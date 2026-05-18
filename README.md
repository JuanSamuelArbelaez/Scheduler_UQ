# Scheduler UQ - Sistema Multiagente de Agenda por Telegram

**Estado: ✅ COMPLETAMENTE FUNCIONAL Y OPERATIVO**

Scheduler es un sistema multiagente avanzado para gestionar agendas personales mediante Telegram con lenguaje natural, recordatorios duales (email + Telegram), y UX moderna con botones interactivos.

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

El proyecto incluye un servidor MCP que sincroniza eventos con Google Calendar.

**Inicio rápido (modo mock):**
```bash
# Terminal 1: Inicia el servidor MCP
python mcp_server/run.py

# Terminal 2: Inicia el bot
python main.py
```

El servidor escucha en `http://localhost:8088/mcp` y los eventos se sincronizan automáticamente.

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
```

**Para sincronización real con Google Calendar:**
1. Crea una cuenta de servicio en [Google Cloud Console](https://console.cloud.google.com)
2. Descarga el JSON de credenciales
3. Configura la variable de entorno:
```bash
export GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/service-account.json
python mcp_server/run.py
```

Ver [mcp_server/README.md](mcp_server/README.md) para más detalles.

## 🎮 Uso en Telegram

### Comandos Disponibles
- `/start` - Menú principal con botones interactivos
- `/agenda` - Ver agenda completa organizada por días
- `/create` - Crear nuevo evento
- `/update` - Modificar evento existente
- `/cancel` - Cancelar evento
- `/health` - Estado del sistema

### Texto Libre Inteligente
El bot entiende lenguaje natural en español:

```
"Agenda una reunión con Ana mañana a las 3:30pm"
"¿Qué tengo programado hoy?"
"Cancela mi cita de las 5"
"Mueve la reunión a mañana 10am"
"Mi zona horaria es UTC-5"
"Configura mi email: usuario@dominio.com"
```

### UX Moderna con Botones
1. Envía `/start` al bot
2. Elige opciones del menú interactivo
3. Confirma acciones críticas
4. Recibe notificaciones naturales

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
