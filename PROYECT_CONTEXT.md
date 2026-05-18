# PROJECT_CONTEXT.md — Scheduler (Sistema Multiagente de Agenda por Telegram)

## 1. Descripción General

**Scheduler** es un Sistema Multiagente (MSA) completamente funcional para gestionar agendas personales mediante Telegram usando lenguaje natural avanzado.

**Estado Actual: ✅ SISTEMA COMPLETO Y OPERATIVO**

Objetivo: permitir operaciones CRUD completas, recordatorios duales (email + Telegram), gestión inteligente por agentes autónomos, y UX moderna con botones interactivos.

El sistema se integra con un bot de Telegram completamente funcional:

* Bot: `t.me/uq_scheduler_bot`
* Token: almacenado de forma segura en **secrets** (no hardcodeado)
* UX Moderna: Botones inline, menús interactivos, navegación intuitiva

---

## 2. Arquitectura FC-MSA - IMPLEMENTADA

Capas completamente implementadas:

1. **Physical Network** → agentes especializados y comunicación robusta
2. **Synchronization** → coordinación perfecta entre agentes
3. **Network Controller** → Orchestrator Agent con lógica avanzada
4. **Assessment** → validación inteligente y análisis de conflictos
5. **Fault Tolerance** → manejo completo de errores y fallbacks

---

## 3. Agentes - COMPLETAMENTE IMPLEMENTADOS

* **Orchestrator Agent** → flujo principal con lógica de coordinación
* **NLP Agent** → parsing avanzado de lenguaje natural en español
* **Intent Agent** → clasificación de intención con Qwen 2.5 + fallback determinístico
* **Scheduling Agent** → gestión completa de agenda con anti-solapamiento inteligente
* **Priority Agent** → asignación automática de prioridades
* **Notification Agent** → plantillas de mensajes naturales y recordatorios
* **Confirmation Agent** → sistema de confirmaciones para acciones críticas
* **User Preferences Agent** → gestión completa de preferencias (email, zona horaria)
* **History Agent** → auditoría completa de todas las acciones

---

## 4. Flujo Completo - OPERATIVO

Usuario → Telegram → **UX Moderna con Botones** → Orchestrator → NLP → Intent → Agente específico → **Confirmación Inteligente** → Ejecución → **Notificación Dual** (Telegram + Email)

### 🔌 Flujo MCP - Google Calendar

Usuario → Telegram → Orchestrator → Scheduling Agent → CalendarSyncService → MCPCalendarProvider → **MCP Server (puerto 8088)** → Google Calendar

**Componentes:**
- **Servidor MCP** (`mcp_server/server.py`): JSON-RPC 2.0 sobre HTTP en puerto 8088
- **GoogleCalendarService**: Interfaz con Google Calendar API (mock o real)
- **MCPRPCRouter**: Enrutador de métodos JSON-RPC
- **MCPCalendarHandler**: Manejador HTTP de solicitudes POST

**Modos de operación:**
1. **Mock Mode** (desarrollo/testing): Sin credenciales de Google, todas las operaciones simuladas
2. **Production Mode** (producción): Con service account de Google, sincronización real

El calendario se asocia al email configurado durante onboarding. Si MCP no está disponible o falla, el sistema mantiene la operación local y registra el incidente en `History`.

---

## 5. Funcionalidades Completas - ✅ IMPLEMENTADAS

### 🎯 Operaciones CRUD Completas
* ✅ Crear evento con parsing inteligente de fechas en español
* ✅ Consultar agenda con formato visual por días
* ✅ Modificar evento con resolución de conflictos
* ✅ Cancelar evento con confirmación

### 🔔 Sistema de Recordatorios Dual
* ✅ Recordatorios por **Telegram** con mensajes formateados en Markdown
* ✅ Recordatorios por **Email** con asuntos y cuerpos profesionales
* ✅ Canales configurables: `telegram`, `email`, `both` (por defecto)
* ✅ Envío automático cada 60 segundos con zona horaria del usuario

### ☁️ Integración MCP / Google Calendar
* ✅ Capa `services/providers` desacoplada para integraciones externas
* ✅ Provider MCP para create/update/delete sincronizados
* ✅ Descubrimiento de `tools`, `templates` y `data sources`
* ✅ Fallback local cuando el provider falla
* ✅ Auditoría de sincronizaciones y fallos en `History`

### ⚡ Anti-Solapamiento Inteligente
* ✅ Detección automática de conflictos
* ✅ Resolución inteligente con sugerencias de slots libres
* ✅ Mensajes informativos sobre conflictos encontrados
* ✅ Re-agendamiento automático en el siguiente espacio disponible

### 🎨 UX Telegram Moderna
* ✅ Menú principal con botones inline interactivos
* ✅ Navegación intuitiva sin comandos complejos
* ✅ Mensajes naturales en español
* ✅ Confirmaciones visuales y retroalimentación inmediata

### 🤖 IA Avanzada Integrada
* ✅ Qwen 2.5 Instruct como modelo principal local
* ✅ Prompts optimizados para clasificación de intención
* ✅ Parsing de fechas en español avanzado
* ✅ Fallback determinístico completo para máxima resiliencia

---

## 6. Modelo de Datos Completo - EXTENDIDO

### Users
* ✅ id (INTEGER PRIMARY KEY)
* ✅ telegram_chat_id (TEXT NOT NULL UNIQUE)
* ✅ email (TEXT)
* ✅ preferences (TEXT DEFAULT '{}') - JSON con timezone, etc.

### Events - MODELO EXTENDIDO
* ✅ id (INTEGER PRIMARY KEY)
* ✅ user_id (INTEGER NOT NULL) → FK users(id) CASCADE
* ✅ title (TEXT NOT NULL)
* ✅ description (TEXT)
* ✅ location (TEXT)
* ✅ start_time (DATETIME NOT NULL)
* ✅ end_time (DATETIME NOT NULL)
* ✅ priority (INTEGER DEFAULT 3)
* ✅ status (TEXT DEFAULT 'scheduled')
* ✅ **source (TEXT DEFAULT 'telegram')** - telegram, web, api
* ✅ **timezone (TEXT DEFAULT 'America/Bogota')** - zona horaria del evento
* ✅ **created_at (DATETIME DEFAULT CURRENT_TIMESTAMP)**
* ✅ **updated_at (DATETIME DEFAULT CURRENT_TIMESTAMP)**
* ✅ **confirmed (BOOLEAN DEFAULT FALSE)**
* ✅ **metadata (JSON DEFAULT '{}')** - datos adicionales flexibles
* ✅ **recurrence_rule (TEXT)** - para futuras expansiones

### Reminders - SISTEMA MULTI-CANAL
* ✅ id (INTEGER PRIMARY KEY)
* ✅ event_id (INTEGER NOT NULL) → FK events(id) CASCADE
* ✅ remind_at (DATETIME NOT NULL)
* ✅ **channel (TEXT DEFAULT 'both')** - telegram, email, both
* ✅ sent_at (DATETIME)
* ✅ delivery_status (TEXT)

### History - AUDITORÍA COMPLETA
* ✅ id (INTEGER PRIMARY KEY)
* ✅ user_id (INTEGER NOT NULL) → FK users(id) CASCADE
* ✅ event_id (INTEGER) → FK events(id) SET NULL
* ✅ action (TEXT NOT NULL) - create, update, cancel, reminder_sent
* ✅ timestamp (DATETIME NOT NULL)
* ✅ details (TEXT) - JSON con detalles de la acción

---

## 7. Tecnologías - STACK COMPLETO

* ✅ **Python 3.13** - versión actualizada
* ✅ **SQLite** - base de datos robusta con migraciones
* ✅ **python-telegram-bot** - framework completo para bots
* ✅ **Qwen 2.5 Instruct** - modelo LLM local optimizado
* ✅ **Ollama** - runtime local para IA
* ✅ **SMTP** - sistema de correo electrónico

---

## 8. Configuración de Secrets - COMPLETA

Variables de entorno implementadas:

```bash
# Obligatorias
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_BOT_URL=https://t.me/uq_scheduler_bot
SQLITE_PATH=scheduler.db

# Funcionalidades
DEFAULT_REMINDER_MINUTES=15
DEFAULT_TIMEZONE=America/Bogota
RUN_TELEGRAM_BOT=true

# IA Local (Opcional pero recomendado)
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct

# Correo Electrónico (Opcional)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=usuario
SMTP_PASSWORD=clave
SMTP_FROM_EMAIL=bot@tu-dominio.com
SMTP_USE_TLS=true

# MCP / Google Calendar
MCP_ENABLED=false
MCP_HTTP_ENDPOINT=http://localhost:8080/mcp
MCP_TIMEOUT_SECONDS=15
MCP_RETRY_COUNT=2
MCP_GOOGLE_CALENDAR_CREATE_TOOL=google_calendar.create_event
MCP_GOOGLE_CALENDAR_UPDATE_TOOL=google_calendar.update_event
MCP_GOOGLE_CALENDAR_DELETE_TOOL=google_calendar.delete_event
MCP_LIST_TOOLS_METHOD=tools/list
MCP_LIST_TEMPLATES_METHOD=prompts/list
MCP_LIST_RESOURCES_METHOD=resources/list
GOOGLE_CALENDAR_ID=
```

---

## 9. Reglas Funcionales - IMPLEMENTADAS

* ✅ **Confirmación obligatoria** para acciones críticas (crear, modificar, cancelar)
* ✅ **Anti-solapamiento inteligente** con resolución automática
* ✅ **No modificar eventos pasados** - validación estricta
* ✅ **Recordatorios duales** - email + Telegram por defecto
* ✅ **Zona horaria por usuario** - soporte completo
* ✅ **Mensajes naturales** - respuestas en español conversacional

---

## 10. IA y Modelos - COMPLETAMENTE INTEGRADO

* ✅ **Interpretación avanzada de lenguaje natural** en español
* ✅ **Manejo de fechas relativas** - "hoy", "mañana", "mediodía", "medianoche"
* ✅ **Resolución de ambigüedad** con preguntas de aclaración
* ✅ **Clasificación de intención** con Qwen 2.5 + fallback determinístico
* ✅ **Prompts optimizados** para máxima precisión

**Validación de Runtime:**
- Si `LLM_PROVIDER=ollama`, valida conectividad y modelo antes de iniciar
- Fallback automático a lógica determinística si IA no disponible
- Sistema completamente funcional con o sin IA local

---

## 11. Fault Tolerance - ROBUSTA

* ✅ **Logs completos** en todas las operaciones
* ✅ **Reintentos automáticos** en envíos de notificaciones
* ✅ **Validación estricta de datos** antes de operaciones
* ✅ **Health check interno** (`SELECT 1` en DB)
* ✅ **Manejo de errores** en todos los agentes
* ✅ **Transacciones seguras** en operaciones críticas

---

## 12. Notificaciones Naturales - ALTAMENTE DESARROLLADAS

Sistema de mensajes conversacionales en español:

* ✅ **Creación**: "Listo, agendé tu reunión 'X' para el Y a las Z"
* ✅ **Modificación**: "Actualicé la cita 'X', ahora es el Y a las Z"
* ✅ **Cancelación**: "Cancelé la cita 'X' que tenías programada"
* ✅ **Conflictos**: "⚠️ Encontré conflicto con 'A', 'B', 'C'. Agendé en el siguiente espacio: D"
* ✅ **Recordatorios**: "🔔 Recordatorio: 'X' comienza en Y minutos"

---

## 13. Telegram - INTEGRACIÓN COMPLETA

**Comandos implementados:**
- ✅ `/start` - Menú principal con botones
- ✅ `/help` - Ayuda completa
- ✅ `/agenda` - Ver agenda formateada
- ✅ `/create` - Crear evento (con parsing inteligente)
- ✅ `/update` - Modificar evento
- ✅ `/cancel` - Cancelar evento
- ✅ `/health` - Estado del sistema

**UX Moderna:**
- ✅ **Botones inline** para navegación intuitiva
- ✅ **Callbacks** para acciones rápidas
- ✅ **Text router** para procesamiento de texto libre
- ✅ **Error handler** con logging automático

---

## 14. MCP / Google Calendar - NUEVO

**Componentes implementados:**
- ✅ `services/providers/calendar_provider.py` - interfaz base de proveedores de calendario
- ✅ `services/providers/mcp_calendar_provider.py` - provider MCP con transporte JSON-RPC
- ✅ `services/calendar_sync_service.py` - orquestación de sincronización, retries y fallback

**Flujo de sincronización:**
1. El usuario configura email y zona horaria en onboarding
2. `SchedulingAgent` crea, actualiza o cancela el evento localmente
3. `CalendarSyncService` intenta sincronizar con Google Calendar vía MCP
4. El provider usa el email del usuario como asociación del calendario
5. Si MCP falla, el sistema conserva la operación local y registra el fallo en `History`

**Capacidades MCP expuestas:**
- `tools` para create/update/delete
- `templates` para plantillas de eventos
- `data sources` para email, timezone y contexto de agenda

---

## 15. Testing - SUITE COMPLETA

**Pruebas de aplicación:**
- ✅ **test_database_operations()** - CRUD completo
- ✅ **test_scheduler_service()** - lógica de negocio
- ✅ **test_reminder_channels()** - sistema multi-canal
- ✅ **test_calendar_sync()** - sincronización MCP
- ✅ **test_llm_integration()** - IA local
- ✅ **test_parsing_functions()** - parsing de fechas
- ✅ **test_full_system()** - integración completa

**Pruebas del servidor MCP:**
- ✅ **test_server.py** (13 tests) - Lógica JSON-RPC, servicios de calendario, herramientas
- ✅ **test_integration.py** (5 tests) - HTTP requests e2e al servidor MCP

**Cobertura:** Base de datos, servicios, agentes, integración MCP, integración LLM, parsing, sistema completo

**Ejecutar todas las pruebas:**
```bash
# Tests de aplicación
python test_system.py

# Tests del servidor MCP
python mcp_server/test_server.py -v
python mcp_server/test_integration.py -v
```

---

## 16. Estado de Producción - ✅ LISTO

**Sistema completamente operativo y probado:**

- ✅ Base de datos con esquema actualizado
- ✅ Todos los agentes implementados y coordinados
- ✅ UX Telegram moderna y funcional
- ✅ Recordatorios duales operativos
- ✅ Anti-solapamiento inteligente
- ✅ IA integrada con fallbacks
- ✅ **Servidor MCP para Google Calendar completamente funcional**
  - Modo mock para testing
  - Modo producción con service account de Google
  - Todos los tests pasando (18 tests totales)
- ✅ Testing completo

**Inicio rápido en producción:**
```bash
# Terminal 1: Servidor MCP
python mcp_server/run.py

# Terminal 2: Bot Telegram
python main.py
```
- ✅ Manejo robusto de errores
- ✅ Configuración segura de secrets

**Próximos pasos opcionales:**
- Despliegue en servidor de producción
- Integración con Google Calendar
- Soporte multi-idioma adicional
- Optimizaciones de rendimiento

* `/start`
* `/help`
* `/agenda`
* `/create titulo | inicio_iso | fin_iso | descripcion`
* `/update id | titulo | inicio_iso | fin_iso | descripcion`
* `/cancel id`
* `/health`

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
* Resolver desambiguación por opciones numeradas cuando hay títulos parecidos
* Validar `/health` y estado `db: ok`

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
* Casos ambiguos (selección por número)
* Errores de formato hora/fecha

## 15. Seguridad DB y Entradas

Controles activos:

* Consultas SQL parametrizadas en repositorios
* Restricción de operaciones SQLite peligrosas (`ATTACH`, `DROP`, `PRAGMA`, `ALTER`) vía authorizer
* Validación de campos de evento para bloquear patrones riesgosos en texto
* Bloqueo de prompts peligrosos en flujo de lenguaje natural del bot

Ejecución:

```bash
python run_tests.py
```
