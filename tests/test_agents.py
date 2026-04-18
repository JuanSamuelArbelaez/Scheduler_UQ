from __future__ import annotations

from datetime import datetime, timedelta
import unittest

from agents.confirmation import ConfirmationAgent
from agents.intent import IntentAgent, IntentType
from agents.nlp import NLPAgent
from agents.notification import NotificationAgent
from agents.orchestrator import OrchestratorAgent
from agents.priority import PriorityAgent
from models.entities import Event, Reminder


class AgentBehaviorTests(unittest.TestCase):
    def test_intent_agent_classifies_core_intents(self) -> None:
        intent_agent = IntentAgent()

        self.assertEqual(intent_agent.classify("programa cita con juan"), IntentType.CREATE)
        self.assertEqual(intent_agent.classify("que tengo manana"), IntentType.READ)
        self.assertEqual(intent_agent.classify("mueve mi cita"), IntentType.UPDATE)
        self.assertEqual(intent_agent.classify("cancela mi cita"), IntentType.DELETE)

    def test_orchestrator_builds_consistent_result(self) -> None:
        orchestrator = OrchestratorAgent(
            nlp=NLPAgent(),
            intent=IntentAgent(),
            priority=PriorityAgent(),
            confirmation=ConfirmationAgent(),
        )

        result = orchestrator.handle("mueve mi cita urgente")

        self.assertEqual(result.intent, IntentType.UPDATE)
        self.assertEqual(result.priority, 1)
        self.assertTrue(result.requires_confirmation)
        self.assertIn("mueve", result.normalized_text)

    def test_notification_agent_formats_messages(self) -> None:
        notification = NotificationAgent()
        start_time = datetime.now() + timedelta(days=1)
        event = Event(
            id=10,
            user_id=1,
            title="Reunion de proyecto",
            description=None,
            location=None,
            start_time=start_time,
            end_time=start_time + timedelta(hours=1),
            priority=3,
        )
        reminder = Reminder(id=1, event_id=10, remind_at=start_time - timedelta(minutes=15))

        create_message = notification.build_creation_message(event, reminder)
        agenda_message = notification.build_agenda_message([event])

        self.assertIn("Listo, agend", create_message)
        self.assertIn("Reunion de proyecto", create_message)
        self.assertIn("Tu agenda actual es:", agenda_message)
        self.assertIn("Reunion de proyecto", agenda_message)


if __name__ == "__main__":
    unittest.main()