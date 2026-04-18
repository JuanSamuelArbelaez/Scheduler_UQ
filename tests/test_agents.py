from __future__ import annotations

from datetime import datetime, timedelta
import unittest
from unittest.mock import Mock, patch

from agents.confirmation import ConfirmationAgent
from agents.intent import IntentAgent, IntentType
from agents.nlp import NLPAgent
from agents.notification import NotificationAgent
from agents.orchestrator import OrchestratorAgent
from agents.priority import PriorityAgent
from models.entities import Event, Reminder
from services.local_llm import LocalOllamaClient


class AgentBehaviorTests(unittest.TestCase):
    def test_intent_agent_classifies_core_intents(self) -> None:
        intent_agent = IntentAgent()

        self.assertEqual(intent_agent.classify("programa cita con juan"), IntentType.CREATE)
        self.assertEqual(intent_agent.classify("que tengo manana"), IntentType.READ)
        self.assertEqual(
            intent_agent.classify(
                "crea una cita para ir el sabado 6 de junio de 2026 al cine, a las 8 pm. voy a ir a ver digital circus"
            ),
            IntentType.CREATE,
        )
        self.assertEqual(intent_agent.classify("mueve mi cita"), IntentType.UPDATE)
        self.assertEqual(intent_agent.classify("cancela mi cita"), IntentType.DELETE)
        self.assertEqual(intent_agent.classify("quiero configurar mi correo electronico asociado"), IntentType.PREFERENCES)
        self.assertEqual(intent_agent.classify("cambiar mi correo en preferencias"), IntentType.PREFERENCES)

    def test_intent_agent_uses_ollama_when_available(self) -> None:
        llm_client = Mock()
        llm_client.classify_intent.return_value = "preferences"
        intent_agent = IntentAgent(llm_client=llm_client)

        self.assertEqual(intent_agent.classify("quiero configurar mi correo"), IntentType.PREFERENCES)
        llm_client.classify_intent.assert_called_once()

    def test_intent_agent_falls_back_when_ollama_returns_unknown(self) -> None:
        llm_client = Mock()
        llm_client.classify_intent.return_value = "unknown"
        intent_agent = IntentAgent(llm_client=llm_client)

        self.assertEqual(intent_agent.classify("cambiar mi correo en preferencias"), IntentType.PREFERENCES)

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

    def test_local_ollama_client_parses_json_decision(self) -> None:
        client = LocalOllamaClient("http://localhost:11434", "llama3.1:8b")

        with patch.object(
            LocalOllamaClient,
            "_post_json",
            return_value={
                "response": '{"action":"create","title":"Reunion","start":"2030-01-01T10:00:00","end":"2030-01-01T11:00:00"}'
            },
        ):
            decision = client.analyze("agenda reunion mañana a las 10")

        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "create")
        self.assertEqual(decision.title, "Reunion")
        self.assertEqual(decision.start, "2030-01-01T10:00:00")

    def test_local_ollama_client_ignores_when_unconfigured(self) -> None:
        client = LocalOllamaClient("http://localhost:11434", "")
        self.assertFalse(client.is_configured())
        self.assertIsNone(client.analyze("agenda reunion mañana a las 10"))

    def test_local_ollama_client_parses_json_decision(self) -> None:
        client = LocalOllamaClient("http://localhost:11434", "llama3.1:8b")

        with patch.object(
            LocalOllamaClient,
            "_post_json",
            return_value={
                "response": '{"action":"create","title":"Reunion","start":"2030-01-01T10:00:00","end":"2030-01-01T11:00:00"}'
            },
        ):
            decision = client.analyze("agenda reunion mañana a las 10")

        self.assertIsNotNone(decision)
        self.assertEqual(decision.action, "create")
        self.assertEqual(decision.title, "Reunion")
        self.assertEqual(decision.start, "2030-01-01T10:00:00")
        self.assertFalse(decision.needs_clarification)

    def test_local_ollama_client_ignores_when_unconfigured(self) -> None:
        client = LocalOllamaClient("http://localhost:11434", "")
        self.assertFalse(client.is_configured())
        self.assertIsNone(client.analyze("agenda reunion mañana a las 10"))


if __name__ == "__main__":
    unittest.main()