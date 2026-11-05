"""Entrada de linha de comando para inspeção e resolução das atividades WL."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
import threading
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from .browser import (
    PORTAL,
    allowed_url,
    all_ava_course_links,
    inspect_quiz_view,
    match_wl_to_ava,
    portal_wl_cards,
    scan_current_course,
    section_urls,
)
from .rules import Activity

if getattr(sys, "frozen", False):
    # O arquivo único é extraído numa pasta temporária; dados de usuários devem
    # sobreviver a cada execução e ficar separados em cada conta Windows.
    ROOT = Path(sys.executable).resolve().parent / "Dados-RoboAVA"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "0"
else:
    ROOT = Path(__file__).resolve().parent.parent
PROFILE_NAME = re.compile(r"[a-zA-Z0-9_-]{1,40}\Z")


def wait_for_enter(page, prompt: str) -> None:
    """Mantém o Playwright ativo enquanto a pessoa interage com o Chrome."""
    ready = threading.Event()

    def read_input() -> None:
        try:
            input(prompt)
        except EOFError:
            pass  # Execuções sem terminal interativo encerram após salvar o relatório.
        finally:
            ready.set()

    threading.Thread(target=read_input, daemon=True).start()
    while not ready.is_set():
        page.wait_for_timeout(250)


def wait_for_wl_courses(context) -> tuple[object, list[tuple[str, str]]]:
    """Cruza os cartões WL do portal com os cursos da aba AVA."""
    print("Faça login manualmente na janela do navegador. Deixe 'Minhas Disciplinas' no portal")
    print("e a lista de cursos do AVA abertas. Depois disso, o programa continua sozinho.")
    last_notice = time.monotonic()
    while True:
        wl_names: list[str] = []
        ava_courses: list[tuple[str, str]] = []
        ava_page = None
        for page in reversed(context.pages):
            for frame in page.frames:
                try:
                    wl_names.extend(portal_wl_cards(frame))
                    found = all_ava_course_links(frame)
                except Exception:
                    continue  # A página pode estar mudando durante o login.
                if found:
                    ava_courses.extend(found)
                    ava_page = page
        matches, unresolved = match_wl_to_ava(wl_names, ava_courses)
        if wl_names and not unresolved and matches and ava_page is not None:
            return ava_page, matches
        if time.monotonic() - last_notice >= 15:
            print(
                f"Ainda aguardando: {len(context.pages)} aba(s), "
                f"{len(set(wl_names))} cartão(ões) WL, {len(ava_courses)} curso(s) AVA. Ctrl+C para sair."
            )
            if unresolved:
                print("Sem correspondente único no AVA: " + "; ".join(unresolved[:8]))
            last_notice = time.monotonic()
        active = next((page for page in context.pages if not page.is_closed()), None)
        if active is None:
            raise SystemExit("A janela do navegador foi fechada.")
        active.wait_for_timeout(500)


def save_report(
    profile_name: str, courses: list[tuple[str, str]], activities: list, scanned_urls: list[str]
) -> Path:
    report = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "profile": profile_name,
        "courses": [{"name": name, "url": url} for name, url in courses],
        "scanned_course_urls": scanned_urls,
        "activities": [asdict(item) for item in activities],
    }
    output = ROOT / ".reports" / f"{profile_name}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)
    return output


def append_progress(profile_name: str, activity: Activity, event: str, details: dict) -> None:
    """Diário local e atômico para retomar após uma interrupção."""
    output = ROOT / ".reports" / f"{profile_name}-progress.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    entries = json.loads(output.read_text(encoding="utf-8")) if output.exists() else []
    entries.append({
        "at": datetime.now(timezone.utc).isoformat(),
        "course": activity.course,
        "unit": activity.unit,
        "kind": activity.kind,
        "url": activity.url,
        "event": event,
        "details": details,
    })
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output)


def unresolved_question_urls(profile_name: str) -> set[str]:
    """Impede reabrir uma atividade com questão comprovadamente ilegível."""
    path = ROOT / ".reports" / f"{profile_name}-progress.json"
    if not path.exists():
        return set()
    blocked: set[str] = set()
    for entry in json.loads(path.read_text(encoding="utf-8")):
        if entry.get("event") == "questão pendente":
            blocked.add(entry["url"])
        elif entry.get("event") == "envio confirmado":
            blocked.discard(entry["url"])
    return blocked


def setup_api_key() -> None:
    """Recebe uma chave sem eco e a guarda na variável de usuário do Windows."""
    try:
        import winreg
    except ImportError as exc:
        raise SystemExit("Este comando de configuração é destinado ao Windows.") from exc
    while True:
        key = getpass.getpass("Cole a chave UMA VEZ (entrada oculta) e pressione Enter: ").strip()
        key = key.replace("\x16", "")  # Alguns terminais incluem o caractere de Ctrl+V ao colar.
        if not key:
            print("Nenhum caractere foi recebido. Copie a chave secreta, clique nesta janela e cole com o botão direito.")
            continue
        if len(key) < 20 or not key.isprintable() or any(char.isspace() for char in key):
            print("O texto recebido está curto ou contém espaços. Nada foi salvo; tente novamente.")
            continue
        if not key.startswith("sk-"):
            print("Isso não parece uma chave OpenAI (ela começa com sk-). Nada foi salvo; tente novamente.")
            continue
        if key.count("sk-") > 1:
            print("Parece haver mais de uma chave colada. Nada foi salvo; tente novamente.")
            continue
        break
    variable = "OPENAI_API_KEY"
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as environment:
        try:
            previous, _ = winreg.QueryValueEx(environment, variable)
        except FileNotFoundError:
            previous = None
        winreg.SetValueEx(environment, variable, 0, winreg.REG_SZ, key)
    print("Chave salva nas variáveis de usuário do Windows. Ela não foi exibida nem escrita no projeto.")
    if previous == key:
        print("A chave colada é IGUAL à que já estava salva.")
    else:
        print("A chave salva é DIFERENTE da anterior.")


def scan_courses(page, courses: list[tuple[str, str]], profile_name: str, timeout_error) -> list[Activity]:
    """Descobre atividades WL e salva o relatório na mesma sessão do navegador."""
    result_by_url: dict[str, Activity] = {}
    scanned_urls: list[str] = []
    diagnostics: list[dict] = []
    for name, url in courses:
        pending = [url]
        visited: set[str] = set()
        while pending and len(visited) < 5:
            section_url = pending.pop(0)
            if section_url in visited:
                continue
            visited.add(section_url)
            try:
                page.goto(section_url, wait_until="domcontentloaded", timeout=20000)
            except timeout_error:
                diagnostics.append({"course": name, "requested_url": section_url, "error": "Tempo esgotado"})
                continue
            if "/course/view.php" not in page.url:
                raise SystemExit("O AVA pediu login novamente. Faça o login manual e repita a leitura.")
            page.wait_for_timeout(1000)
            for next_url in section_urls(page, url):
                if next_url not in visited and next_url not in pending:
                    pending.append(next_url)
            activities = scan_current_course(page, name)
            for activity in activities:
                result_by_url[activity.url] = activity
            first = page.locator('a[href*="/mod/quiz/view.php"]').first
            diagnostics.append({
                "course": name,
                "requested_url": section_url,
                "landed_url": page.url,
                "headings": page.locator("h1").all_inner_texts()[:5],
                "next_unit_urls": section_urls(page, url),
                "activity_titles": [item.title for item in activities],
                "first_activity_html": first.evaluate(
                    "a => (a.parentElement?.parentElement?.parentElement || a.parentElement).outerHTML.slice(0, 10000)"
                ) if first.count() else "",
            })
            debug_output = ROOT / ".reports" / f"{profile_name}-diagnostic.json"
            debug_output.parent.mkdir(parents=True, exist_ok=True)
            debug_output.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
            save_report(profile_name, courses, list(result_by_url.values()), scanned_urls)
        scanned_urls.append(url)
        save_report(profile_name, courses, list(result_by_url.values()), scanned_urls)
    result = list(result_by_url.values())
    if not result:
        raise SystemExit("Nenhuma atividade do escopo foi encontrada. Verifique o login e a lista do AVA.")
    print(f"{len(courses)} matérias (WL), {len(result)} atividades identificadas.")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspeciona cursos (WL) no AVA")
    parser.add_argument("command", choices=("open", "scan", "status", "solve", "run", "setup-key"))
    parser.add_argument("--profile", default="principal", help="Nome local do perfil, sem espaços")
    parser.add_argument("--model", default=None, help="Modelo OpenAI; padrão gpt-6-luna")
    parser.add_argument("--question-delay", type=float, default=0, help="Pausa em segundos entre questões; padrão: 0")
    parser.add_argument("--max-activities", type=int, default=0, help="Limita o número de atividades nesta execução")
    args = parser.parse_args()
    if not PROFILE_NAME.fullmatch(args.profile):
        parser.error("--profile deve conter só letras, números, _ ou - (até 40 caracteres)")
    if args.max_activities < 0:
        parser.error("--max-activities deve ser zero ou positivo")
    if not 0 <= args.question_delay <= 60:
        parser.error("--question-delay deve estar entre 0 e 60 segundos")
    if args.command == "setup-key":
        setup_api_key()
        return

    solver = None
    if args.command in ("solve", "run"):
        try:
            from .openai_solver import OpenAISolver

            solver = OpenAISolver(args.model)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc

    try:
        from playwright.sync_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError, sync_playwright
    except ImportError as exc:
        raise SystemExit("Instale as dependências: python -m pip install -r requirements.txt") from exc

    profile = ROOT / ".profiles" / args.profile
    profile.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser_options = {"user_data_dir": str(profile), "headless": False}
        if not getattr(sys, "frozen", False):
            browser_options["channel"] = "chrome"
        context = playwright.chromium.launch_persistent_context(**browser_options)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            try:
                page.goto(PORTAL, wait_until="domcontentloaded")
            except PlaywrightError:
                print("O portal demorou para responder. Tente abrir ou atualizar a página no navegador.")
            if args.command == "open":
                wait_for_enter(page, "Navegador aberto. Faça o login manualmente; pressione Enter para fechar. ")
                return

            page, courses = wait_for_wl_courses(context)
            if args.command == "run":
                report_path = ROOT / ".reports" / f"{args.profile}.json"
                scanned_urls = []
                if report_path.exists():
                    scanned_urls = json.loads(report_path.read_text(encoding="utf-8")).get("scanned_course_urls", [])
                if set(scanned_urls) != {url for _, url in courses}:
                    scan_courses(page, courses, args.profile, PlaywrightTimeoutError)
                args.command = "solve"
            if args.command in ("status", "solve"):
                report_path = ROOT / ".reports" / f"{args.profile}.json"
                if not report_path.exists():
                    raise SystemExit("Ainda não há relatório deste perfil. Execute scan primeiro.")
                previous = json.loads(report_path.read_text(encoding="utf-8"))
                expected = {url for _, url in courses}
                recorded = {course["url"] for course in previous["courses"]}
                if expected != recorded:
                    raise SystemExit("As matérias WL desta sessão diferem do relatório. Execute scan novamente.")
                activities = [Activity(**item) for item in previous["activities"]]
                scanned_urls = previous.get("scanned_course_urls", [])
                if args.command == "solve":
                    from .attempt import run_activity
                    from .answer_validation import CannotAnswer

                    attempted = 0
                    blocked_urls = unresolved_question_urls(args.profile)
                    for index, item in enumerate(activities):
                        if item.status == "concluída":
                            continue
                        if item.url in blocked_urls:
                            print(f"Questão ilegível registrada; pulando {item.course} | U{item.unit} | {item.kind}")
                            continue
                        if args.max_activities and attempted >= args.max_activities:
                            break
                        attempted += 1
                        print(f"{attempted} | {item.course} | U{item.unit} | {item.kind}", flush=True)
                        log = lambda event, details, current=item: append_progress(args.profile, current, event, details)
                        try:
                            status, grade = run_activity(
                                page, item, solver, log, ROOT / ".reports" / f"{args.profile}-pending",
                                question_delay=args.question_delay,
                            )
                            activities[index] = replace(item, status=status, grade=grade)
                        except Exception as exc:
                            log("pendência", {"reason": str(exc)})
                            print(f"Pendência: {exc}", flush=True)
                            try:
                                page.goto(item.url, wait_until="domcontentloaded", timeout=20000)
                                if "/mod/quiz/view.php" not in page.url:
                                    raise SystemExit("A sessão expirou. Faça login manual antes de retomar.")
                                page.wait_for_timeout(500)
                                fresh_status, fresh_grade = inspect_quiz_view(page)
                                activities[index] = replace(item, status=fresh_status, grade=fresh_grade)
                            except PlaywrightTimeoutError:
                                pass
                            save_report(args.profile, courses, activities, scanned_urls)
                            if not isinstance(exc, CannotAnswer):
                                raise SystemExit(
                                    "Erro de integração interrompeu a execução; o estado foi salvo. "
                                    f"Detalhes: {exc}"
                                ) from exc
                            continue
                        save_report(args.profile, courses, activities, scanned_urls)
                    print(f"Progresso salvo: {ROOT / '.reports' / f'{args.profile}-progress.json'}")
                    wait_for_enter(page, "Execução encerrada. Pressione Enter para fechar o navegador. ")
                    return
                print(f"Conferindo {len(activities)} questionários sem abrir tentativas...")
                for index, item in enumerate(activities, start=1):
                    if not allowed_url(item.url):
                        continue
                    try:
                        page.goto(item.url, wait_until="domcontentloaded", timeout=20000)
                    except PlaywrightTimeoutError:
                        print(f"{index}/{len(activities)} | Tempo esgotado | {item.course} U{item.unit} {item.kind}")
                        continue
                    if "/mod/quiz/view.php" not in page.url:
                        raise SystemExit("O AVA pediu login novamente. Faça o login manual e repita status.")
                    page.wait_for_timeout(1000)
                    status, grade = inspect_quiz_view(page)
                    if status == "verificar no portal":
                        diagnostic_path = ROOT / ".reports" / f"{args.profile}-quiz-diagnostic.json"
                        diagnostic_path.write_text(json.dumps({
                            "requested_url": item.url,
                            "landed_url": page.url,
                            "title": page.title(),
                            "body_excerpt": page.locator("body").inner_text()[:2500],
                            "html_excerpt": page.locator("body").inner_html()[:5000],
                        }, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(f"Estado não reconhecido; diagnóstico salvo em {diagnostic_path}.")
                        break
                    activities[index - 1] = replace(item, status=status, grade=grade)
                    save_report(args.profile, courses, activities, scanned_urls)
                    print(f"{index}/{len(activities)} | {item.course} | U{item.unit} | {item.kind} | {status} | {grade}")
                print(f"Relatório atualizado: {report_path}")
                wait_for_enter(page, "Conferência concluída. Pressione Enter para fechar o navegador. ")
                return
            result = scan_courses(page, courses, args.profile, PlaywrightTimeoutError)
            output = ROOT / ".reports" / f"{args.profile}.json"
            print(f"Relatório: {output}")
            for item in result:
                print(f"{item.course} | U{item.unit} | {item.kind} | {item.status}")
            wait_for_enter(page, "Leitura concluída. Pressione Enter para fechar o navegador. ")
        finally:
            try:
                context.close()
            except Exception:
                pass  # O driver pode já ter fechado após Ctrl+C.


if __name__ == "__main__":
    main()
