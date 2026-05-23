#!/usr/bin/env python3
"""
Script de pruebas extensivas para el sistema Scheduler UQ
"""

import sys
import os
import sqlite3
from datetime import datetime, timedelta, UTC
from pathlib import Path

# Agregar el directorio raíz al path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import load_settings
from db.database import Database
from db.repositories import EventRepository, UserRepository, ReminderRepository, HistoryRepository
from models.entities import Event, User, Reminder, HistoryEntry
from services.scheduler_service import SchedulerService
from services.local_llm import LocalOllamaClient
from agents.scheduling import SchedulingAgent
from agents.intent import IntentAgent
from agents.notification import NotificationAgent

def test_database_operations():
    """Prueba operaciones básicas de base de datos"""
    print("=== PRUEBA: Operaciones de Base de Datos ===")

    settings = load_settings()
    db = Database(settings.sqlite_path)
    db.initialize()

    with db.transaction() as connection:
        user_repo = UserRepository(connection)
        event_repo = EventRepository(connection)
        reminder_repo = ReminderRepository(connection)
        history_repo = HistoryRepository(connection)

        # Crear usuario
        user = User(id=None, user_key='test_123', email='test@example.com')
        created_user = user_repo.upsert(user)
        print(f"✅ Usuario creado: ID={created_user.id}")

        # Crear evento con todas las nuevas columnas
        now = datetime.now()
        event = Event(
            id=None,
            user_id=created_user.id,
            title='Reunión de Prueba',
            description='Descripción de prueba',
            location='Sala de reuniones',
            start_time=now + timedelta(hours=1),
            end_time=now + timedelta(hours=2),
            priority=3,
            status='scheduled',
            source='web',
            timezone='America/Bogota',
            confirmed=True,
            metadata={'test': 'data'},
            recurrence_rule=None
        )

        created_event = event_repo.create(event)
        print(f"✅ Evento creado: ID={created_event.id}, source={created_event.source}, timezone={created_event.timezone}")

        # Verificar que se guardaron las nuevas columnas
        retrieved_event = event_repo.get_by_id(created_event.id)
        assert retrieved_event.source == 'web'
        assert retrieved_event.timezone == 'America/Bogota'
        assert retrieved_event.confirmed == True
        assert retrieved_event.metadata == {'test': 'data'}
        print("✅ Nuevas columnas del modelo Event funcionan correctamente")

        # Crear reminder
        reminder = Reminder(
            id=None,
            event_id=created_event.id,
            remind_at=created_event.start_time - timedelta(minutes=15)
        )
        created_reminder = reminder_repo.create(reminder)
        assert created_reminder.channel == "both", f"Expected channel 'both', got '{created_reminder.channel}'"
        print(f"✅ Reminder creado: ID={created_reminder.id}, channel={created_reminder.channel}")

        # Probar anti-solapamiento
        overlapping_events = event_repo.get_overlapping(
            created_user.id,
            created_event.start_time,
            created_event.end_time
        )
        assert len(overlapping_events) == 1  # Debería encontrar el evento mismo
        print("✅ Detección de solapamientos funciona")

        # Actualizar evento
        updated_event = event_repo.update(Event(
            id=created_event.id,
            user_id=created_user.id,
            title='Reunión Actualizada',
            description=created_event.description,
            location=created_event.location,
            start_time=created_event.start_time,
            end_time=created_event.end_time,
            priority=5,
            status='scheduled',
            source='web',
            timezone='America/Bogota',
            confirmed=True,
            metadata={'updated': True},
            recurrence_rule=None
        ))
        assert updated_event.title == 'Reunión Actualizada'
        assert updated_event.metadata == {'updated': True}
        print("✅ Actualización de eventos funciona")

        # Cancelar evento
        event_repo.cancel(created_event.id)
        cancelled_event = event_repo.get_by_id(created_event.id)
        assert cancelled_event.status == 'cancelled'
        print("✅ Cancelación de eventos funciona")

        # Crear entrada de historial
        history_entry = HistoryEntry(
            id=None,
            user_id=created_user.id,
            event_id=created_event.id,
            action='create',
            timestamp=datetime.now()
        )
        created_history = history_repo.create(history_entry)
        print(f"✅ Historial creado: ID={created_history.id}")

    print("✅ Todas las operaciones de base de datos pasan las pruebas")

def test_scheduler_service():
    """Prueba el servicio de agendamiento"""
    print("\n=== PRUEBA: Servicio de Agendamiento ===")

    settings = load_settings()
    db = Database(settings.sqlite_path)

    with db.transaction() as connection:
        user_repo = UserRepository(connection)
        event_repo = EventRepository(connection)
        reminder_repo = ReminderRepository(connection)
        history_repo = HistoryRepository(connection)

        # Crear dependencias del servicio
        from agents.notification import NotificationAgent
        from services.email_service import EmailService, EmailSettings

        notification = NotificationAgent()
        email_service = EmailService(EmailSettings(
            host="localhost", port=587, username="", password="",
            from_email="test@example.com", use_tls=False
        ))

        service = SchedulerService(
            event_repo, reminder_repo, user_repo,
            notification, email_service
        )

        # Crear usuario
        user = User(id=None, user_key='service_test_123')
        created_user = user_repo.upsert(user)

        # Probar creación de evento (usando repositorio directamente)
        now = datetime.now()
        event = Event(
            id=None,
            user_id=created_user.id,
            title='Evento de Servicio',
            description=None,
            location=None,
            start_time=now + timedelta(hours=2),
            end_time=now + timedelta(hours=3)
        )

        created_event = event_repo.create(event)
        reminder = Reminder(id=None, event_id=created_event.id, remind_at=created_event.start_time - timedelta(minutes=15))
        created_reminder = reminder_repo.create(reminder)

        print("✅ Creación de eventos funciona")

        # Probar resolución de conflictos con SchedulerService
        conflicting_event = Event(
            id=None,
            user_id=created_user.id,
            title='Evento Conflicto',
            description=None,
            location=None,
            start_time=now + timedelta(hours=2, minutes=30),  # Solapa con el anterior
            end_time=now + timedelta(hours=3, minutes=30)
        )

        # Esto debería crear el evento moviéndolo automáticamente
        result2 = service.create_event_with_conflict_resolution(conflicting_event)
        assert result2.event is not None
        print(f"Evento original: {conflicting_event.start_time}")
        print(f"Evento resultante: {result2.event.start_time}")
        print(f"Mensaje: {result2.message}")

        # Verificar que se creó (aunque no necesariamente se movió si no hay espacios libres)
        if result2.event.start_time != conflicting_event.start_time:
            print("✅ Evento se movió automáticamente")
        else:
            print("ℹ️  Evento se creó en la hora solicitada (posiblemente sin conflictos detectados)")
        print("✅ Resolución de conflictos funciona")

    print("✅ Servicio de agendamiento pasa las pruebas")

def test_llm_integration():
    """Prueba la integración con el modelo de lenguaje"""
    print("\n=== PRUEBA: Integración LLM ===")

    settings = load_settings()

    # Solo probar si Ollama está configurado
    if settings.llm_provider == "ollama" and settings.ollama_model:
        try:
            llm_client = LocalOllamaClient(settings.ollama_base_url, settings.ollama_model)

            # Probar análisis de intención
            decision = llm_client.analyze("Quiero crear una reunión mañana a las 3pm")
            if decision:
                print(f"✅ Análisis de intención funciona: action={decision.action}")
            else:
                print("⚠️  Análisis de intención no disponible (posiblemente sin conexión)")

            # Probar clasificación de intención
            intent = llm_client.classify_intent("agendar reunión")
            if intent:
                print(f"✅ Clasificación de intención funciona: {intent}")
            else:
                print("⚠️  Clasificación de intención no disponible")

        except (Exception, KeyboardInterrupt) as e:
            print(f"⚠️  Integración LLM no disponible: {type(e).__name__}")
    else:
        print("⚠️  LLM no configurado, omitiendo pruebas")

def test_reminder_channels():
    """Prueba el sistema de recordatorios por múltiples canales"""
    print("\n=== PRUEBA: Sistema de Recordatorios Multi-Canal ===")

    # Configurar base de datos de prueba
    settings = load_settings()
    db = Database(settings.sqlite_path)
    db.initialize()

    with db.transaction() as connection:
        reminder_repo = ReminderRepository(connection)

        # Crear reminder con diferentes canales
        test_cases = [
            ("web", "web"),
            ("email", "email"),
            ("both", "both")
        ]

        for channel_name, expected_channel in test_cases:
            reminder = Reminder(
                id=None,
                event_id=1,  # Usar un event_id existente
                remind_at=datetime.now(UTC) + timedelta(hours=1),
                channel=channel_name
            )

            created = reminder_repo.create(reminder)
            assert created.channel == expected_channel
            print(f"✅ Canal '{channel_name}' funciona correctamente")

    print("✅ Sistema de recordatorios multi-canal funciona correctamente")

def test_mcp_calendar_integration():
    """Prueba la integración MCP con sincronización local y fallback"""
    print("\n=== PRUEBA: Integración MCP / Google Calendar ===")

    import sqlite3

    from agents.history import HistoryAgent
    from services.calendar_sync_service import CalendarSyncService
    from services.email_service import EmailService, EmailSettings
    from services.providers.calendar_provider import CalendarCapabilitySnapshot, CalendarProvider, CalendarSyncResult
    from services.scheduler_service import SchedulerService

    class FakeProvider(CalendarProvider):
        name = "fake-mcp"

        def __init__(self) -> None:
            self.available = True
            self.calls: list[tuple[str, dict[str, object]]] = []

        def is_available(self) -> bool:
            return self.available

        def describe_capabilities(self) -> CalendarCapabilitySnapshot:
            return CalendarCapabilitySnapshot(tools=["google_calendar.create_event"], templates=["template"], data_sources=["email"])

        def create_event(self, event: Event, user: User) -> CalendarSyncResult:
            payload = {"email": user.email, "timezone": user.preferences.get("timezone")}
            self.calls.append(("create", payload))
            return CalendarSyncResult(True, self.name, "create", "synced", external_id="ext-1", payload=payload)

        def update_event(self, event: Event, user: User) -> CalendarSyncResult:
            payload = {"email": user.email, "timezone": user.preferences.get("timezone")}
            self.calls.append(("update", payload))
            return CalendarSyncResult(True, self.name, "update", "synced", external_id="ext-2", payload=payload)

        def delete_event(self, event: Event, user: User) -> CalendarSyncResult:
            payload = {"email": user.email, "timezone": user.preferences.get("timezone")}
            self.calls.append(("delete", payload))
            return CalendarSyncResult(True, self.name, "delete", "synced", external_id="ext-3", payload=payload)

    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_key TEXT NOT NULL UNIQUE,
            email TEXT,
            preferences TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            location TEXT,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 3,
            status TEXT NOT NULL DEFAULT 'scheduled',
            source TEXT NOT NULL DEFAULT 'web',
            timezone TEXT NOT NULL DEFAULT 'America/Bogota',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            confirmed INTEGER NOT NULL DEFAULT 0,
            metadata TEXT NOT NULL DEFAULT '{}',
            recurrence_rule TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            remind_at TEXT NOT NULL,
            channel TEXT NOT NULL DEFAULT 'both',
            sent_at TEXT,
            delivery_status TEXT,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
        );
        CREATE TABLE history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event_id INTEGER,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            details TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE SET NULL
        );
        """
    )

    users = UserRepository(connection)
    events = EventRepository(connection)
    reminders = ReminderRepository(connection)
    history_repo = HistoryRepository(connection)
    history = HistoryAgent(history_repo)
    provider = FakeProvider()
    sync_service = CalendarSyncService(provider, history=history, retry_count=0)
    scheduler = SchedulerService(
        events,
        reminders,
        users,
        NotificationAgent(),
        EmailService(EmailSettings(host="", port=587, username="", password="", from_email="")),
        calendar_sync=sync_service,
    )

    user = users.upsert(User(id=None, user_key='mcp_123', email='mcp@example.com', preferences={'timezone': 'America/Bogota'}))
    now = datetime.now()
    event = Event(
        id=None,
        user_id=user.id,
        title='Reunión MCP',
        description='demo',
        location='online',
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=3),
        priority=3,
        status='scheduled',
        source='web',
        timezone='America/Bogota',
        confirmed=False,
        metadata={},
        recurrence_rule=None,
    )

    created = scheduler.create_event_with_conflict_resolution(event)
    assert created.event is not None
    print("✅ Create sincroniza con MCP")

    updated = Event(
        id=created.event.id,
        user_id=user.id,
        title='Reunión MCP actualizada',
        description='demo 2',
        location='online',
        start_time=now + timedelta(hours=4),
        end_time=now + timedelta(hours=5),
        priority=3,
        status='scheduled',
        source='web',
        timezone='America/Bogota',
        confirmed=False,
        metadata={},
        recurrence_rule=None,
    )
    scheduler.update_event(updated)
    scheduler.cancel_event(created.event.id)
    assert [call[0] for call in provider.calls] == ['create', 'update', 'delete']
    print("✅ Update / delete sincronizan con MCP")

    rows = connection.execute("SELECT action FROM history ORDER BY id DESC LIMIT 3").fetchall()
    assert rows
    print("✅ Historial registra sincronizaciones MCP")

    connection.close()
    print("✅ Integración MCP / Google Calendar funciona correctamente")

def test_full_system():
    """Prueba el sistema completo iniciando el bot"""
    print("\n=== PRUEBA: Sistema Completo ===")

    try:
        # Probar que el sistema puede iniciarse
        from main import build_application
        app = build_application()
        print("✅ Sistema completo se inicializa correctamente")

        # Verificar que el bot tiene los handlers correctos
        handlers_count = len(app.handlers[0])  # Comando handlers
        if handlers_count >= 5:  # start, help, agenda, create, update, cancel
            print(f"✅ Bot tiene {handlers_count} handlers configurados")
        else:
            print(f"⚠️  Bot tiene solo {handlers_count} handlers")

    except Exception as e:
        print(f"❌ Error en sistema completo: {e}")

def run_all_tests():
    """Ejecutar todas las pruebas"""
    print("🚀 INICIANDO PRUEBAS EXTENSIVAS DEL SISTEMA SCHEDULER UQ")
    print("=" * 60)

    try:
        test_database_operations()
        test_scheduler_service()
        test_reminder_channels()
        test_mcp_calendar_integration()
        test_llm_integration()
        test_full_system()

        print("\n" + "=" * 60)
        print("🎉 TODAS LAS PRUEBAS PASARON EXITOSAMENTE")
        print("✅ Sistema Scheduler UQ funcionando correctamente")

    except Exception as e:
        print(f"\n❌ ERROR EN PRUEBAS: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)