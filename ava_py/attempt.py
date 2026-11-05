"""Navegação de tentativas do Moodle, com verificação antes de qualquer envio."""

from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .browser import inspect_quiz_view
from .answer_validation import CannotAnswer


def extract_question(question) -> dict:
    """Lê texto e alternativas da questão atualmente exibida."""
    return question.evaluate(
        """q => {
          const clean = s => (s || '').replace(/\\s+/g, ' ').trim();
          const rich = node => {
            if (!node) return '';
            if (node.nodeType === Node.TEXT_NODE) return node.textContent || '';
            if (node.nodeName === 'IMG') return ' [imagem: ' + (node.alt || 'sem descrição') + '] ';
            if (node.nodeName === 'SVG') return ' [fórmula: ' + (node.getAttribute('aria-label') || 'ver imagem') + '] ';
            return [...node.childNodes].map(rich).join(' ');
          };
          const radios = [...q.querySelectorAll('input[type="radio"]')];
          return {
            number: clean(q.querySelector('.qno, h3')?.innerText || ''),
            stem: clean(rich(q.querySelector('.qtext') || q.querySelector('.formulation'))),
            radio_groups: [...new Set(radios.map(radio => radio.name))].length,
            options: radios.map((radio, index) => {
              const label = radio.labels?.[0] ||
                (radio.id ? q.querySelector('label[for="' + CSS.escape(radio.id) + '"]') : null);
              const container = label || radio.closest('.r0, .r1') || radio.parentElement;
              const text = clean(rich(container) || radio.getAttribute('aria-label') || '')
                .replace(/^[a-z]\\.\\s*/i, '');
              return {index, text, checked: radio.checked};
            }),
            images: [...q.querySelectorAll('.formulation img')].map(img => ({
              alt: img.alt || '', loaded: img.complete && img.naturalWidth > 0
            }))
          };
        }"""
    )


def verify_summary(rows: list[dict]) -> None:
    """Exige uma linha salva para cada pergunta realmente listada no resumo."""
    if not rows:
        raise CannotAnswer("O resumo da tentativa não mostrou a lista de perguntas.")
    for row in rows:
        if not re.fullmatch(r"\d+", row.get("question", "").strip()):
            raise CannotAnswer("O resumo contém uma pergunta sem número identificável.")
        if "resposta salva" not in row.get("status", "").casefold():
            raise CannotAnswer(f"Pergunta {row['question']} não consta como resposta salva no resumo.")


def summary_rows(page) -> list[dict]:
    return page.locator("body").evaluate(
        """body => {
          for (const table of body.querySelectorAll('table')) {
            const heads = [...table.querySelectorAll('thead th')]
              .map(th => (th.innerText || '').trim().toLowerCase());
            const question = heads.indexOf('pergunta');
            const status = heads.indexOf('status');
            if (question < 0 || status < 0) continue;
            return [...table.querySelectorAll('tbody tr')].map(tr => {
              const cells = [...tr.querySelectorAll('td')].map(td => (td.innerText || '').trim());
              return {question: cells[question] || '', status: cells[status] || ''};
            });
          }
          return [];
        }"""
    )


def _attempt_page(page) -> bool:
    return urlparse(page.url).path == "/mod/quiz/attempt.php"


def _summary_page(page) -> bool:
    return urlparse(page.url).path == "/mod/quiz/summary.php"


def first_attempt_url(current_url: str) -> str:
    """Retorna a primeira página da própria tentativa em andamento."""
    parsed = urlparse(current_url)
    attempt = parse_qs(parsed.query).get("attempt", [""])[0]
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.avaeduc.com.br"
        or parsed.path not in ("/mod/quiz/attempt.php", "/mod/quiz/summary.php")
        or not attempt.isdigit()
    ):
        raise CannotAnswer("Não foi possível identificar a primeira página desta tentativa.")
    return f"https://www.avaeduc.com.br/mod/quiz/attempt.php?attempt={attempt}"


def run_activity(
    page, activity, solver, log, pending_dir: Path | None = None, *, question_delay: float = 0
) -> tuple[str, str]:
    """Retoma ou inicia uma tentativa; envia somente após resumo integralmente salvo."""
    page.goto(activity.url, wait_until="domcontentloaded", timeout=25000)
    if urlparse(page.url).path != "/mod/quiz/view.php":
        raise CannotAnswer("A sessão do AVA expirou antes de abrir o questionário.")
    page.wait_for_timeout(700)
    status, grade = inspect_quiz_view(page)
    if status == "concluída":
        log("já concluída", {"grade": grade})
        return status, grade
    if status == "em andamento":
        button = page.get_by_role("button", name="Continuar a última tentativa")
    elif status == "pendente":
        button = page.get_by_role("button", name="Tentar responder o questionário agora")
    else:
        raise CannotAnswer("Não foi possível confirmar se a atividade está pendente ou em andamento.")
    if button.count() != 1:
        raise CannotAnswer("Botão para abrir a tentativa não encontrado de forma única.")
    button.click()
    page.wait_for_load_state("domcontentloaded")
    log("tentativa aberta", {"state_before": status, "url": page.url})
    first_url = first_attempt_url(page.url)
    if page.url != first_url:
        page.goto(first_url, wait_until="domcontentloaded", timeout=25000)
        log("retomada na primeira questão", {"url": page.url})

    visited_pages: set[str] = set()
    answered_count = 0
    for _ in range(100):
        if _summary_page(page):
            break
        if not _attempt_page(page):
            raise CannotAnswer("A navegação saiu da tentativa de forma inesperada.")
        if page.url in visited_pages:
            raise CannotAnswer("A navegação voltou à mesma página da tentativa.")
        visited_pages.add(page.url)
        questions = page.locator(".que:visible")
        count = questions.count()
        if count == 0:
            raise CannotAnswer("A página da tentativa não mostrou nenhuma questão legível.")
        for position in range(count):
            if answered_count and question_delay:
                time.sleep(question_delay)
            block = questions.nth(position)
            screenshot = block.screenshot(type="png", timeout=15000)
            data = extract_question(block)
            if not data["options"] or data["radio_groups"] != 1 or any(not image["loaded"] for image in data["images"]):
                raise CannotAnswer("Questão sem alternativas de seleção única ou com imagem ilegível.")
            try:
                decision = solver.answer(course=activity.course, question=data, screenshot=screenshot)
            except CannotAnswer as exc:
                details = {
                    "question": data["number"], "reason": str(exc),
                    "stem": data["stem"], "options": [option["text"] for option in data["options"]],
                }
                if pending_dir is not None:
                    pending_dir.mkdir(parents=True, exist_ok=True)
                    quiz_id = page.url.split("attempt=")[-1].split("&")[0]
                    question_id = re.sub(r"\W+", "-", data["number"]).strip("-")
                    shot_path = pending_dir / f"{quiz_id}-{question_id}.png"
                    shot_path.write_bytes(screenshot)
                    details["screenshot"] = str(shot_path)
                log("questão pendente", details)
                raise
            radio = block.locator('input[type="radio"]').nth(decision.index)
            radio.check()
            if not radio.is_checked():
                raise CannotAnswer("A alternativa escolhida não permaneceu marcada.")
            log("resposta marcada", {
                "page": page.url,
                "question": data["number"],
                "option_text": decision.text,
                "explanation": decision.explanation,
            })
            answered_count += 1
        next_button = page.get_by_role("button", name="Próxima página")
        finish_button = page.get_by_role("button", name=re.compile(r"Finalizar tentativa"))
        if next_button.count() == 1:
            next_button.click()
        elif finish_button.count() == 1:
            finish_button.click()
        else:
            raise CannotAnswer("Não foi encontrado um único botão de navegação ou finalização.")
        page.wait_for_load_state("domcontentloaded")
    else:
        raise CannotAnswer("A tentativa excedeu 100 páginas; interrompida por segurança.")

    verify_summary(summary_rows(page))
    log("resumo conferido", {"url": page.url})
    send = page.get_by_role("button", name="Enviar tudo e terminar")
    if send.count() != 1:
        raise CannotAnswer("Botão de envio não encontrado no resumo.")
    send.click()
    dialog = page.get_by_role("dialog")
    try:
        dialog.wait_for(state="visible", timeout=10000)
    except Exception as exc:
        raise CannotAnswer("A confirmação de envio não apareceu como esperado.") from exc
    if dialog.count() != 1:
        raise CannotAnswer("A confirmação de envio não apareceu como esperado.")
    confirm = dialog.get_by_role("button", name="Enviar tudo e terminar")
    if confirm.count() != 1:
        raise CannotAnswer("Botão de confirmação não encontrado de forma única.")
    log("confirmação apresentada", {"url": page.url})
    confirm.click()
    page.wait_for_timeout(1200)
    # Consulta o estado antes de qualquer nova ação; nunca repete o envio às cegas.
    page.goto(activity.url, wait_until="domcontentloaded", timeout=25000)
    page.wait_for_timeout(700)
    final_status, final_grade = inspect_quiz_view(page)
    if final_status != "concluída":
        raise CannotAnswer("O envio não pôde ser confirmado na página do questionário.")
    log("envio confirmado", {"grade": final_grade})
    return final_status, final_grade
