# Scheduler

Scheduler es un sistema multiagente para gestionar agendas por Telegram con lenguaje natural.

## Qué hace

- Crear, consultar, modificar y cancelar citas
- Pedir confirmación antes de acciones críticas
- Resolver ambigüedades por texto libre
- Funcionar con fallback por reglas si no hay LLM local disponible
- Clasificar intenciones con Ollama (incluye preferencias como email/UTC)
- Enviar correos por acción (crear, actualizar, cancelar) y recordatorios por email
- Configurar zona horaria por usuario (default: Colombia)
- Ejecutar un health check interno al iniciar

## Requisitos

- Python 3.13
- SQLite
- Cuenta y bot de Telegram
- Opcional para IA local: Ollama instalado y modelo descargado

## Configuración

1. Copia [.env.example](.env.example) a [.env](.env) y ajusta los valores.
2. Define al menos:

```bash
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_BOT_URL=https://t.me/uq_scheduler_bot
SQLITE_PATH=scheduler.db
DEFAULT_REMINDER_MINUTES=15
DEFAULT_TIMEZONE=America/Bogota
RUN_TELEGRAM_BOT=true
```

## LLM local opcional

Si quieres soporte local adicional para extracción y ambigüedad:

```bash
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

Puedes usar otro modelo local compatible con Ollama, por ejemplo:

- `llama3.1:8b`
- `qwen2.5:7b-instruct`
- `mistral:7b-instruct`

Si el modelo no está disponible o Ollama no responde, el bot vuelve al flujo determinístico por reglas.

## Correo y recordatorios

Configura SMTP para activar notificaciones y recordatorios por email:

```bash
SMTP_HOST=smtp.tu-proveedor.com
SMTP_PORT=587
SMTP_USERNAME=usuario
SMTP_PASSWORD=clave
SMTP_FROM_EMAIL=bot@tu-dominio.com
SMTP_USE_TLS=true
```

Con SMTP activo, el sistema envía correo cuando:

- Se crea una cita
- Se actualiza una cita
- Se cancela una cita
- Se dispara un recordatorio

## Instalación

Instala dependencias:

```bash
python -m pip install -r requirements.txt
```

## Ejecutar el proyecto

### Modo normal

Inicializa la base y muestra el health check:

```bash
python main.py
```

### Modo bot Telegram

Activa el polling del bot. Si `TELEGRAM_BOT_TOKEN` está configurado, `main.py` inicia el bot automáticamente:

```bash
python main.py
```

Asegúrate de tener `TELEGRAM_BOT_TOKEN` en `.env`. `RUN_TELEGRAM_BOT=true` sigue siendo válido, pero ya no es obligatorio si hay token.

## Probar en Telegram

1. Abre el bot configurado en Telegram.
2. Envía `/start`.
3. En el primer contacto, configura email y zona horaria cuando el bot lo solicite.
4. Prueba con texto natural:
   - `programa reunion con ana manana a las 15:30`
   - `cancela reunion semanal`
   - `mueve la cita 3 a manana 18:00`
   - `quiero configurar mi correo electrónico asociado: correo@dominio.com`
   - `mi zona horaria es UTC-5`
5. Responde `si`, `no` o el número de opción si el sistema pide desambiguación.

## Pruebas

Ejecuta la suite:

```bash
python run_tests.py
```

## Comandos útiles

- `/agenda`
- `/create`
- `/update`
- `/cancel`
- `/health`

## Arquitectura

El proyecto usa agentes simbólicos con persistencia SQLite y un proveedor LLM local opcional para mejorar la comprensión del lenguaje natural.
