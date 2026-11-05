"""Regras de seleção independentes do navegador e da conta do aluno."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


WL = re.compile(r"\bWL\b", re.IGNORECASE)
UNIT = re.compile(r"\bU\s*([1-4])\b|\bUNIDADE\s*([1-4])\b", re.IGNORECASE)
TYPES = (
    ("Atividade de Aprendizagem", "atividade de aprendizagem"),
    ("Avaliação da Unidade", "avaliacao da unidade"),
)
TITLE = re.compile(
    r"^(?:u\s*[1-4]\s*[-–:]?\s*)?"
    r"(atividade de aprendizagem|avaliacao da unidade)(?:\b|$)"
)


@dataclass(frozen=True)
class Activity:
    course: str
    unit: int
    kind: str
    title: str
    url: str
    status: str
    grade: str = ""


def quiz_view_status(tables: list[dict], buttons: list[str]) -> tuple[str, str]:
    """Classifica somente sinais da tabela de tentativas e botões da página inicial."""
    for table in tables:
        headers = [normalize(value) for value in table.get("headers", [])]
        if "estado" not in headers:
            continue
        state_index = headers.index("estado")
        grade_index = next((i for i, title in enumerate(headers) if title.startswith("nota")), None)
        for row in table.get("rows", []):
            if state_index < len(row) and normalize(row[state_index]).startswith("finalizada"):
                grade = row[grade_index].strip() if grade_index is not None and grade_index < len(row) else ""
                return "concluída", grade
    for table in tables:
        headers = [normalize(value) for value in table.get("headers", [])]
        if "estado" in headers:
            index = headers.index("estado")
            if any(index < len(row) and normalize(row[index]).startswith("em progresso") for row in table.get("rows", [])):
                return "em andamento", ""
    names = [normalize(name) for name in buttons]
    if any("continuar a ultima tentativa" in name for name in names):
        return "em andamento", ""
    if any("tentar responder o questionario agora" in name for name in names):
        return "pendente", ""
    return "verificar no portal", ""


def normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in plain if not unicodedata.combining(char))
    return " ".join(plain.casefold().split())


def is_wl_course(name: str) -> bool:
    return bool(WL.search(name))


def activity_identity(title: str, section: str = "") -> tuple[int, str] | None:
    """Aceita só os dois questionários pedidos, nas unidades 1 a 4."""
    normalized = normalize(title)
    title_match = TITLE.match(normalized)
    if not title_match:
        return None
    kind = next(label for label, text in TYPES if text == title_match.group(1))
    match = UNIT.search(title) or UNIT.search(section)
    if not match:
        return None
    return int(match.group(1) or match.group(2)), kind


def completion_status(markers: list[str]) -> str:
    """Só um sinal explícito de conclusão permite pular automaticamente."""
    marker_text = normalize(" ".join(markers))
    if any(phrase in marker_text for phrase in ("nao concluido", "nao concluida", "nao enviado", "nao feito", "not completed", "completion-auto-n", "completion-manual-n")):
        return "verificar no portal"
    if any(word in marker_text for word in ("concluido", "concluida", "finalizado", "enviado", "feito", "completed", "completion-auto-y", "completion-manual-y", "fa-check")):
        return "concluída"
    return "verificar no portal"
