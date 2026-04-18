from __future__ import annotations


class PriorityAgent:
    name = "priority"

    def assign(self, text: str) -> int:
        normalized = text.lower()
        if any(keyword in normalized for keyword in ("urgente", "asap", "hoy mismo")):
            return 1
        if any(keyword in normalized for keyword in ("importante", "prioritario")):
            return 2
        return 3