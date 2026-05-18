# Guía de Inicio Rápido - MCP Server + Scheduler UQ

## 🎯 ¿Qué se logró?

Se implementó un **servidor MCP completo** que sincroniza eventos de Telegram con Google Calendar. El servidor funciona en modo mock (sin credenciales) para testing, y en producción se usa OAuth por usuario para enlazar cada calendario personal.

## ⚡ Inicio en 2 Minutos (Modo Mock)

```bash
# Terminal 1: Inicia el servidor MCP
python mcp_server/run.py

# Esperas el mensaje: "MCP server listening on http://localhost:8088/mcp"
```

```bash
# Terminal 2: Inicia el bot Telegram
python main.py
```

¡Listo! El sistema está corriendo. Los eventos que crees en Telegram se sincronizarán con el calendario (en modo mock).

## 🔧 Configuración

El `.env` ya está preconfigurado con:
- `MCP_ENABLED=true` ✅
- `MCP_HTTP_ENDPOINT=http://localhost:8088/mcp` ✅
- Todas las herramientas necesarias configuradas

## 📝 Flujo de Uso

1. Usuario en Telegram: "Almuerzo mañana a las 2pm"
2. Bot: Confirma la cita
3. Sistema: 
   - ✅ Guarda localmente en SQLite
   - ✅ Sincroniza con Google Calendar vía MCP (si está disponible)
   - ✅ Registra la sincronización en History

Si el MCP server no está disponible, el evento se guarda localmente y se registra el intento fallido.

## 🧪 Tests

```bash
# Tests del servidor MCP (unit)
python mcp_server/test_server.py -v
# Resultado: 13 tests ✅

# Tests de integración HTTP
python mcp_server/test_integration.py -v
# Resultado: 5 tests ✅

# Tests de la aplicación
python test_system.py
# Incluye: test_mcp_calendar_integration() ✅
```

## 📦 Componentes Nuevos

```
mcp_server/
├── server.py              # Servidor JSON-RPC HTTP
├── run.py                 # Launcher del servidor
├── test_server.py         # 13 tests unitarios
├── test_integration.py    # 5 tests de integración
├── README.md              # Documentación detallada
├── requirements.txt       # Dependencias (google-api-python-client, etc)
└── __init__.py
```

## 🚀 Para Producción: Google Calendar Real

```bash
# 1. Crea un OAuth Client ID en https://console.cloud.google.com
# 2. Descarga el JSON de credenciales OAuth

# 3. Configura la variable de entorno:
export GOOGLE_OAUTH_CLIENT_SECRETS_FILE=/path/to/oauth-client-secrets.json

# 4. Inicia el servidor MCP:
python mcp_server/run.py

# 5. Inicia el bot y completa el onboarding de Google Calendar desde Telegram:
python main.py
```

Los eventos ahora se sincronizarán en **tiempo real** con el calendario personal autorizado por cada usuario.

## 🔍 Ver Logs

El servidor imprime información detallada:

```
INFO:root:Starting MCP Calendar Server on localhost:8088
INFO:root:Running in MOCK mode - no real Google Calendar sync
INFO:root:MCP server listening on http://localhost:8088/mcp
```

Si usa credenciales reales:
```
INFO:root:Connected to real Google Calendar API
```

## 🆘 Troubleshooting

### "Connection refused" desde Telegram
- Verifica que el servidor MCP está corriendo: `python mcp_server/run.py`
- Verifica que escucha en puerto 8088
- Verifica que `.env` tiene `MCP_HTTP_ENDPOINT=http://localhost:8088/mcp`

### "Sincronización Google Calendar no disponible"
- El servidor MCP no está corriendo
- O está configurado un puerto diferente
- En modo mock, esto es comportamiento normal (fallback local)

### Tests fallan
```bash
# Instala dependencias del servidor
pip install -r mcp_server/requirements.txt

# Ejecuta los tests con verbose
python mcp_server/test_server.py -v
```

## 📚 Documentación Completa

- Arquitectura del servidor: `mcp_server/README.md`
- Contexto del proyecto: `PROYECT_CONTEXT.md`
- README principal: `README.md`
- Configuración del bot: `.env` (ve la sección `MCP_*`)

## ✅ Verificación Rápida

```bash
# 1. Ver estado del git
git log --oneline | head -3

# 2. Verificar estructura del proyecto
ls -la mcp_server/

# 3. Ver últimas pruebas
python mcp_server/test_server.py -v 2>&1 | grep -E "^test_|OK|FAILED"
```

## 🎓 Siguientes Pasos

1. **Configurar Google Calendar real** (opcional)
2. **Agregar autenticación de usuarios** (opcional)
3. **Expandir herramientas MCP** (más operaciones de calendario)

---

**Estado**: ✅ **Completamente funcional y listo para usar**

Creado: 18 de Mayo de 2026
Servidor: JSON-RPC HTTP sobre localhost:8088
Tests: 18 tests totales, todos pasando
