from __future__ import annotations

from dataclasses import dataclass

from .confirmation import ConfirmationAgent
from .intent import IntentAgent, IntentType
from .nlp import NLPAgent
from .priority import PriorityAgent


@dataclass(slots=True)
class OrchestrationResult:
    intent: IntentType
    normalized_text: str
    priority: int
    requires_confirmation: bool


class OrchestratorAgent:
    name = "orchestrator"

    def __init__(self, nlp: NLPAgent, intent: IntentAgent, priority: PriorityAgent, confirmation: ConfirmationAgent) -> None:
        self.nlp = nlp
        self.intent = intent
        self.priority = priority
        self.confirmation = confirmation

    def handle(self, text: str) -> OrchestrationResult:
        parsed = self.nlp.parse(text)
        detected_intent = self.intent.classify(parsed.normalized_text)
        priority = self.priority.assign(parsed.normalized_text)
        requires_confirmation = self.confirmation.requires_confirmation(detected_intent)
        return OrchestrationResult(
            intent=detected_intent,
            normalized_text=parsed.normalized_text,
            priority=priority,
            requires_confirmation=requires_confirmation,
        )