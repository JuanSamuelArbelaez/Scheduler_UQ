from __future__ import annotations

from abc import ABC, abstractmethod


class Agent(ABC):
    name: str

    @abstractmethod
    def handle(self, payload: dict[str, object]) -> dict[str, object]:
        raise NotImplementedError