from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from .confirmation import ConfirmationAgent
from .intent import IntentAgent, IntentType
from .nlp import NLPAgent
from .priority import PriorityAgent
from services.providers.calendar_provider import CalendarCapabilitySnapshot, CalendarProvider


@dataclass(slots=True)
class OrchestrationResult:
    intent: IntentType
    normalized_text: str
    priority: int
    requires_confirmation: bool
    calendar_capabilities: CalendarCapabilitySnapshot = field(default_factory=CalendarCapabilitySnapshot)


class OrchestratorAgent:
    name = "orchestrator"

    def __init__(
        self,
        nlp: NLPAgent,
        intent: IntentAgent,
        priority: PriorityAgent,
        confirmation: ConfirmationAgent,
        calendar_provider: CalendarProvider | None = None,
    ) -> None:
        self.nlp = nlp
        self.intent = intent
        self.priority = priority
        self.confirmation = confirmation
        self.calendar_provider = calendar_provider

    def handle(self, text: str) -> OrchestrationResult:
        parsed = self.nlp.parse(text)
        detected_intent = self.intent.classify(parsed.normalized_text)
        priority = self.priority.assign(parsed.normalized_text)
        requires_confirmation = self.confirmation.requires_confirmation(detected_intent)
        calendar_capabilities = self.calendar_provider.describe_capabilities() if self.calendar_provider is not None else CalendarCapabilitySnapshot()
        return OrchestrationResult(
            intent=detected_intent,
            normalized_text=parsed.normalized_text,
            priority=priority,
            requires_confirmation=requires_confirmation,
            calendar_capabilities=calendar_capabilities,
        )