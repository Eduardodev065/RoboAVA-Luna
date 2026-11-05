"""Validação da escolha retornada pelo resolvedor."""

from __future__ import annotations

from dataclasses import dataclass

from .rules import normalize


@dataclass(frozen=True)
class Decision:
    index: int  # Índice baseado em zero, válido somente para a questão atual.
    text: str
    explanation: str


class CannotAnswer(ValueError):
    """Falta informação ou a resposta não foi fundamentada."""


def validate_decision(raw: dict, options: list[str]) -> Decision:
    if raw.get("answerable") is not True:
        raise CannotAnswer(str(raw.get("missing_information") or "A resposta não foi fundamentada."))
    choice = raw.get("choice_index")
    if type(choice) is not int or not 1 <= choice <= len(options):
        raise CannotAnswer("O índice retornado não corresponde às alternativas visíveis.")
    text = str(raw.get("choice_text") or "").strip()
    actual = options[choice - 1].strip()
    if actual and normalize(text) != normalize(actual):
        raise CannotAnswer("O texto escolhido difere da alternativa nessa posição.")
    explanation = str(raw.get("explanation") or "").strip()
    if len(explanation) < 20:
        raise CannotAnswer("A justificativa é insuficiente para marcar a alternativa.")
    return Decision(index=choice - 1, text=actual, explanation=explanation)
