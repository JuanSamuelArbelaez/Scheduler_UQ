from __future__ import annotations

from .intent import IntentType


class ConfirmationAgent:
    name = "confirmation"

    def requires_confirmation(self, intent: IntentType) -> bool:
        return intent in {IntentType.CREATE, IntentType.UPDATE, IntentType.DELETE}