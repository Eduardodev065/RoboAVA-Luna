"""Leitura do AVA com Chrome visível; nenhuma tentativa é aberta aqui."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from .rules import Activity, activity_identity, completion_status, is_wl_course, normalize, quiz_view_status

PORTAL = "https://alunodigital.unic.br/pda_unic"
AVA_HOST = "www.avaeduc.com.br"


def allowed_url(url: str, *, course: bool = False) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != AVA_HOST:
        return False
    expected = "/course/view.php" if course else "/mod/quiz/view.php"
    return parsed.path == expected


def course_candidates(page) -> list[dict]:
    """Lê nomes do link e do cartão que o envolve."""
    return page.locator('a[href*="/course/view.php"]').evaluate_all(
        """links => links.map(a => {
          const card = a.closest('.coursebox, .coursecard, [data-region="course-content"], article, li');
          return {
            name: (a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '').trim(),
            cardName: (card?.querySelector('.coursename, .course-name')?.innerText || card?.innerText || '').trim(),
            url: a.href
          };
        })"""
    )


def course_links(page) -> list[tuple[str, str]]:
    """Lê os cursos exibidos na página atual; não adivinha uma lista fixa."""
    found = course_candidates(page)
    unique: dict[str, str] = {}
    for item in found:
        name, url = item["name"], item["url"]
        if not is_wl_course(name):
            name = item["cardName"]
        if is_wl_course(name) and allowed_url(url, course=True):
            unique[url] = name
    return [(name, url) for url, name in unique.items()]


def all_ava_course_links(page) -> list[tuple[str, str]]:
    """Lista cursos do AVA mesmo quando ele omite a etiqueta WL."""
    unique: dict[str, str] = {}
    for item in course_candidates(page):
        name = item["name"] or item["cardName"]
        if name and allowed_url(item["url"], course=True):
            unique[item["url"]] = name
    return [(name, url) for url, name in unique.items()]


def portal_wl_cards(frame) -> list[str]:
    """Busca a etiqueta WL nos cartões 'Minhas Disciplinas' do portal."""
    found = frame.locator("body").evaluate(
        """body => {
          const result = [];
          const leafs = [...body.querySelectorAll('*')].filter(el =>
            el.childElementCount === 0 && /\\bWL\\b/i.test(el.textContent || '')
          );
          for (const leaf of leafs) {
            let node = leaf;
            while (node && node !== body) {
              const lines = (node.innerText || '').split(/\\n+/).map(x => x.trim())
                .filter(x => x && !/^[•⋮.]+$/.test(x));
              const labels = lines.filter(x => /[-–]\\s*WL\\b/i.test(x));
              const label = lines.findIndex(x => /[-–]\\s*WL\\b/i.test(x));
              if (labels.length === 1 && label === 0 && lines.length > 1) {
                const stop = lines.findIndex((x, i) => i > label && /^(ACESSAR A DISCIPLINA|AGUARDE)$/i.test(x));
                const name = lines.slice(label + 1, stop < 0 ? undefined : stop).join(' ').trim();
                if (name) result.push(name);
                break;
              }
              node = node.parentElement;
            }
          }
          return [...new Set(result)];
        }"""
    )
    return found


def match_wl_to_ava(cards: list[str], courses: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], list[str]]:
    """Só aceita correspondências únicas entre o nome do cartão e o curso AVA."""
    matched: list[tuple[str, str]] = []
    unresolved: list[str] = []
    for name in dict.fromkeys(cards):
        options = list({url: (ava_name, url) for ava_name, url in courses if normalize(ava_name) == normalize(name)}.values())
        if len(options) == 1:
            matched.append(options[0])
        else:
            unresolved.append(name)
    return matched, unresolved


def section_urls(page, course_url: str) -> list[str]:
    """Lê os links reais de navegação 'Unidade de Ensino 1–4'."""
    course_id = parse_qs(urlparse(course_url).query).get("id", [None])[0]
    if not course_id:
        return []
    found = page.locator('a[href*="/course/view.php"][href*="topic="]').evaluate_all(
        "els => els.map(a => ({url: a.href, text: a.innerText.trim()}))"
    )
    unique: dict[str, None] = {}
    for item in found:
        url = item["url"]
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        unit_match = re.search(r"unidade(?: de ensino)?\s*([1-4])\b", normalize(item["text"]))
        if (
            allowed_url(url, course=True)
            and query.get("id", [None])[0] == course_id
            and unit_match
        ):
            unique[url] = None
    return list(unique)


def activity_rows(page) -> list[dict]:
    """Extrai metadados visíveis dos links de questionário de um curso Moodle."""
    return page.locator('a[href*="/mod/quiz/view.php"]').evaluate_all(
        """links => links.map(a => {
          const row = a.closest('li.activity, .activity, [data-region="activity-information"]') || a.parentElement;
          const section = a.closest('li.section, section.course-section, .course-section');
          const heading = section?.querySelector('.sectionname, .section-title, h3, h4');
          const completion = row?.querySelectorAll(
            '.completion-icon, .completion-info, .activity-completion, .automatic-completion-conditions, [data-region="completion-info"]'
          ) || [];
          const markers = [...completion].flatMap(el => [
            el.innerText || '', el.getAttribute('aria-label') || '', el.getAttribute('title') || '',
            ...[...el.querySelectorAll('img, svg, span, i')].flatMap(child => [
              child.getAttribute('alt') || '', child.getAttribute('aria-label') || '',
              child.getAttribute('title') || '', child.getAttribute('src') || '',
              child.getAttribute('class') || ''
            ])
          ]);
          return {
            title: (a.innerText || '').trim(), url: a.href,
            section: (heading?.innerText || '').trim(), markers
          };
        })"""
    )


def scan_current_course(page, course_name: str) -> list[Activity]:
    activities: dict[str, Activity] = {}
    for row in activity_rows(page):
        url = urljoin(page.url, row["url"])
        identity = activity_identity(row["title"], row["section"])
        if not identity or not allowed_url(url):
            continue
        unit, kind = identity
        activities[url] = Activity(
            course=course_name,
            unit=unit,
            kind=kind,
            title=row["title"],
            url=url,
            status=completion_status(row["markers"]),
        )
    return sorted(activities.values(), key=lambda a: (a.unit, a.kind, a.title))


def inspect_quiz_view(page) -> tuple[str, str]:
    """Lê o resumo do questionário sem iniciar nem continuar tentativas."""
    data = page.locator("body").evaluate(
        """body => ({
          tables: [...body.querySelectorAll('table')].map(table => ({
            headers: [...table.querySelectorAll('thead th')].map(th => th.innerText.trim()),
            rows: [...table.querySelectorAll('tbody tr')].map(tr =>
              [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))
          })),
          buttons: [...body.querySelectorAll('button, input[type=submit]')].map(el =>
            (el.innerText || el.value || '').trim())
        })"""
    )
    return quiz_view_status(data["tables"], data["buttons"])
