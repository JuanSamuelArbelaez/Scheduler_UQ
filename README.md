# Scheduler UQ - Web App Local (Flask + MCP)

**Estado: ✅ Rama de migración activa a interfaz web local**

Scheduler es un sistema multiagente para gestionar agendas personales con lenguaje natural, ahora orientado a interfaz web local en Flask. En esta rama se trabaja solo en la versión MCP.

## Nota de Rama

- Esta rama reemplaza el canal Telegram por una interfaz HTML local.
- Incluye login, registro, OTP por correo y onboarding obligatorio con OAuth Google Calendar.
- Mantiene sincronización de calendario via MCP.
- Soporta chat por texto y audio (Whisper STT), y escucha de respuestas con TTS local.

## ✨ Características Principales

### 🎯 Gestión Completa de Agenda
- ✅ **Crear eventos** con parsing inteligente de fechas en español
- ✅ **Consultar agenda** con formato visual organizado por días
- ✅ **Modificar eventos** con resolución automática de conflictos
- ✅ **Cancelar eventos** con confirmación inteligente

### 🔔 Recordatorios Duales Avanzados
- ✅ **Recordatorios por Telegram** con mensajes formateados en Markdown
- ✅ **Recordatorios por Email** con plantillas profesionales
- ✅ **Canales configurables**: `telegram`, `email`, `both` (por defecto)
- ✅ **Envío automático** cada 60 segundos respetando zona horaria del usuario

### ⚡ Anti-Solapamiento Inteligente
- ✅ **Detección automática** de conflictos entre eventos
- ✅ **Resolución inteligente** con sugerencias de slots libres
- ✅ **Re-agendamiento automático** en el siguiente espacio disponible
- ✅ **Mensajes informativos** sobre conflictos encontrados

### 🎨 UX Telegram Moderna
- ✅ **Botones inline interactivos** para navegación intuitiva
- ✅ **Menú principal** con opciones visuales
- ✅ **Mensajes naturales** en español conversacional
- ✅ **Confirmaciones visuales** y retroalimentación inmediata

### 🤖 IA Avanzada Integrada
- ✅ **Qwen 2.5 Instruct** como modelo principal local
- ✅ **Parsing de fechas** en español: "hoy", "mañana", "mediodía", "medianoche"
- ✅ **Clasificación de intención** con IA + fallback determinístico
- ✅ **Resolución de ambigüedad** con preguntas inteligentes

## 🚀 Inicio Rápido

### 1. Clona y configura
```bash
git clone <repository-url>
cd scheduler-uq
cp .env.example .env
```

### 2. Configura variables esenciales
```bash
# Obligatorio
TELEGRAM_BOT_TOKEN=tu_token_aqui
SQLITE_PATH=scheduler.db

# Recomendado
DEFAULT_TIMEZONE=America/Bogota
DEFAULT_REMINDER_MINUTES=15
RUN_TELEGRAM_BOT=true
```

### 3. Instala dependencias
```bash
pip install -r requirements.txt
```

### 4. Ejecuta el sistema
```bash
python main.py
```

## ⚙️ Configuración Avanzada

### IA Local con Ollama (Recomendado)
```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct
```

### Recordatorios por Email
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=tu-email@gmail.com
SMTP_PASSWORD=tu-app-password
SMTP_FROM_EMAIL=tu-email@gmail.com
SMTP_USE_TLS=true
```

### Google Calendar vía MCP

El proyecto incluye un servidor MCP que actúa como puente HTTP/JSON-RPC hacia Google Calendar. Scheduler usa esa capa para desacoplar la app de Telegram de la API externa y mantener la base local como fuente de verdad.

**Inicio rápido (modo mock):**
```bash
# Terminal 1: Inicia el servidor MCP
python mcp_server/run.py

# Terminal 2: Inicia el bot
python main.py
```

El servidor escucha en `http://localhost:8088/mcp` y los eventos se sincronizan automáticamente a través de MCP cuando la integración está habilitada.

**Variables de configuración:**
```bash
MCP_ENABLED=true
MCP_HTTP_ENDPOINT=http://localhost:8088/mcp
MCP_TIMEOUT_SECONDS=15
MCP_RETRY_COUNT=2
MCP_GOOGLE_CALENDAR_CREATE_TOOL=google_calendar.create_event
MCP_GOOGLE_CALENDAR_UPDATE_TOOL=google_calendar.update_event
MCP_GOOGLE_CALENDAR_DELETE_TOOL=google_calendar.delete_event
GOOGLE_CALENDAR_ID=tu_calendario@gmail.com
GOOGLE_OAUTH_CLIENT_SECRETS_FILE=C:\ruta\a\oauth-client-secrets.json
GOOGLE_OAUTH_REDIRECT_PORT=8765
```

**Para sincronización real con Google Calendar:**
1. Crea un proyecto en [Google Cloud Console](https://console.cloud.google.com)
2. Habilita Google Calendar API
3. Crea un OAuth Client ID para aplicación de escritorio
4. Descarga el JSON de credenciales OAuth
5. Configura `GOOGLE_OAUTH_CLIENT_SECRETS_FILE` en `.env`
6. Inicia el bot y completa el onboarding desde Telegram para autorizar el calendario personal del usuario

La conexión se guarda por usuario en SQLite y se usa para sincronizar sus eventos al calendario `primary` de Google, sin mezclar calendarios entre usuarios.

Ver [mcp_server/README.md](mcp_server/README.md) para más detalles.

## 💻 Uso Web Local

### Flujo de acceso
1. Regístrate con usuario, correo y contraseña.
2. Verifica correo con OTP enviado por email.
3. Inicia sesión.
4. Completa onboarding: zona horaria + conexión Google Calendar.

### Chat con el agente
- Campo de texto para mensajes libres.
- Botón de grabación para enviar audio (Whisper STT).
- El agente responde en texto.
- Cada respuesta del asistente incluye botón para escucharla con TTS local.

## 🏗️ Arquitectura

### Agentes Especializados
- **Orchestrator Agent** - Coordinación principal
- **NLP Agent** - Procesamiento de lenguaje natural
- **Intent Agent** - Clasificación de intenciones
- **Scheduling Agent** - Gestión de agenda y conflictos
- **Notification Agent** - Recordatorios y mensajes
- **Confirmation Agent** - Confirmaciones de seguridad
- **User Preferences Agent** - Configuración de usuario
- **History Agent** - Auditoría completa

### Modelo de Datos Extendido
```sql
Users: id, telegram_chat_id, email, preferences
Events: id, user_id, title, description, location, start_time, end_time, priority, status, source, timezone, created_at, updated_at, confirmed, metadata, recurrence_rule
Reminders: id, event_id, remind_at, channel, sent_at, delivery_status
History: id, user_id, event_id, action, timestamp, details
```

### Flujo MCP
```text
Telegram → Orchestrator → SchedulingAgent → CalendarSyncService → MCPCalendarProvider → Google Calendar
```

El provider MCP expone herramientas, plantillas y data sources cuando el gateway las soporta. Si la sincronización externa falla, Scheduler mantiene el comportamiento local y registra el incidente.

## 🧪 Testing Completo

Ejecuta la suite completa de pruebas:

```bash
python test_system.py
```

**Pruebas incluidas:**
- ✅ Operaciones de base de datos
- ✅ Servicio de agendamiento
- ✅ Sistema de recordatorios multi-canal
- ✅ Integración con LLM local
- ✅ Funciones de parsing
- ✅ Sistema completo
- ✅ Integración MCP / Google Calendar

## 🔧 Tecnologías

- **Python 3.13**
- **SQLite** con migraciones automáticas
- **python-telegram-bot** para integración completa
- **Qwen 2.5 Instruct** vía Ollama para IA local
- **SMTP** para notificaciones por email

## 📊 Estado del Sistema

**✅ COMPLETAMENTE OPERATIVO**

- Base de datos con esquema actualizado
- Todos los agentes implementados y coordinados
- UX Telegram moderna funcional
- Recordatorios duales operativos
- Anti-solapamiento inteligente
- IA integrada con fallbacks robustos
- Testing completo y validado
- Manejo robusto de errores
- Configuración segura de secrets

## 🤝 Contribución

1. Fork el proyecto
2. Crea una rama para tu feature
3. Añade tests para nuevas funcionalidades
4. Asegura que todas las pruebas pasen
5. Envía un pull request

## 📝 Licencia

Este proyecto está bajo la Licencia MIT.

---

**🚀 Listo para uso en producción con todas las funcionalidades avanzadas implementadas.**
