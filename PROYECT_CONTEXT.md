# PROJECT_CONTEXT.md — Scheduler (Sistema Multiagente de Agenda por Telegram)

## 1. Descripción General

**Scheduler** es un Sistema Multiagente (MSA) para gestionar agendas personales mediante Telegram usando lenguaje natural.

Objetivo: permitir operaciones CRUD, recordatorios y gestión inteligente por agentes autónomos.

El sistema se integra con un bot de Telegram:

* Bot: `t.me/uq_scheduler_bot`
* Token: almacenado de forma segura en **secrets** (no hardcodeado)

---

## 2. Arquitectura FC-MSA

Capas:

1. Physical Network → agentes y comunicación
2. Synchronization → coordinación y asignación de tareas
3. Network Controller → orquestación
4. Assessment → validación y análisis
5. Fault Tolerance → manejo de errores

---

## 3. Agentes

* **Orchestrator Agent** → flujo principal
* **NLP Agent** → interpreta lenguaje natural
* **Intent Agent** → clasifica intención (CRUD)
* **Scheduling Agent** → gestiona agenda
* **Priority Agent** → asigna prioridad
* **Notification Agent** → envía recordatorios
* **Confirmation Agent** → solicita confirmación
* **User Preferences Agent** → preferencias usuario
* **History Agent** → auditoría

---

## 4. Flujo

Usuario → Telegram → Orchestrator → NLP → Intent → Agente específico → Confirmación → Ejecución → Notificación

---

## 5. Casos de uso

* Crear evento
* Consultar agenda
* Modificar evento
* Cancelar evento
* Gestionar preferencias

---

## 6. Modelo de Datos

### Users

* id
* telegram_chat_id
* email
* preferences

### Events

* id
* user_id
* title
* description
* location
* start_time
* end_time
* priority
* status

### Reminders

* id
* event_id
* remind_at
* channel

### History

* id
* user_id
* event_id
* action
* timestamp
* details

---

## 7. Tecnologías

* Python 3.13
* SQLite
* python-telegram-bot

---

## 8. Configuración de Secrets

Las credenciales del bot **NO deben estar en el código fuente**.

Se deben almacenar en variables de entorno o un gestor de secretos:

```bash
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_BOT_URL=https://t.me/uq_scheduler_bot
```

Opciones recomendadas:

* `.env` (para desarrollo)
* Secret Manager (producción)
* Docker secrets / Kubernetes secrets

### Variables locales del proyecto

El proyecto ya contempla carga automática de `.env` desde la raíz del workspace.

Variables usadas actualmente:

* `SQLITE_PATH` → ruta de la base SQLite
* `DEFAULT_REMINDER_MINUTES` → minutos por defecto para recordatorio
* `TELEGRAM_BOT_TOKEN` → token del bot
* `TELEGRAM_BOT_URL` → URL pública del bot
* `RUN_TELEGRAM_BOT` → habilita el polling del bot en desarrollo

Se recomienda mantener un archivo `.env.example` para valores de referencia y no versionar `.env`.

---

## 9. Reglas

* Confirmación obligatoria para acciones críticas
* No solapar eventos
* No modificar eventos pasados
* Recordatorio default: 15 minutos antes

---

## 10. IA

* Interpretación de lenguaje natural
* Manejo de fechas relativas
* Resolución de ambigüedad

---

## 11. Fault Tolerance

* Logs
* Reintentos
* Validación de datos

## 13. Notificaciones Naturales

Tras agendar, modificar o cancelar una cita, el sistema genera mensajes en lenguaje natural para devolverlos al usuario por Telegram.

Ejemplos:

* "Listo, agendé ..."
* "Actualicé la cita ..."
* "Cancelé la cita ..."

---

## 12. Extensiones

* Google Calendar
* Multi-idioma
* Optimización de agenda

## 13. Telegram

El proyecto ya incluye una capa inicial de integración con `python-telegram-bot`.

Comandos soportados en la base actual:

* `/start`
* `/help`
* `/agenda`
* `/create titulo | inicio_iso | fin_iso | descripcion`
* `/update id | titulo | inicio_iso | fin_iso | descripcion`
* `/cancel id`

El arranque del polling se controla con `RUN_TELEGRAM_BOT=true`.

## 14. Estado de Pruebas

El proyecto está listo para una prueba funcional inicial en Telegram con comandos estructurados.

También incluye flujo conversacional por lenguaje natural con confirmación explícita.

### Checklist mínimo

* Configurar `.env` con token y `RUN_TELEGRAM_BOT=true`
* Instalar dependencias con `pip install -r requirements.txt`
* Ejecutar `python main.py`

### Qué validar

* Crear cita con `/create`
* Consultar agenda con `/agenda`
* Actualizar cita con `/update`
* Cancelar cita con `/cancel`
* Ver mensajes naturales luego de cada acción
* Crear/modificar/cancelar por texto libre con confirmación "si/no"

### Módulo de pruebas

Se añadió un módulo de pruebas automáticas para agentes y bot de Telegram:

* `tests/test_agents.py`
* `tests/test_telegram_bot.py`
* `run_tests.py`

Cobertura actual del módulo de pruebas:

* Clasificación de intención y orquestación
* Formato de notificaciones
* Parsing de lenguaje natural (create/update/cancel)
* Flujo conversacional end-to-end (texto libre -> confirmación -> ejecución)

Ejecución:

```bash
python run_tests.py
```
