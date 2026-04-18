from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ParsedMessage:
    raw_text: str
    normalized_text: str
    tokens: list[str]


class NLPAgent:
    name = "nlp"

    def parse(self, text: str) -> ParsedMessage:
        normalized_text = " ".join(text.strip().split())
        tokens = normalized_text.lower().split(" ") if normalized_text else []
        return ParsedMessage(raw_text=text, normalized_text=normalized_text, tokens=tokens)