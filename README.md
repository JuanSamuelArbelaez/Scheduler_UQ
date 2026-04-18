# Scheduler

Scheduler es un sistema multiagente para gestionar agendas por Telegram con lenguaje natural.

## Qué hace

- Crear, consultar, modificar y cancelar citas
- Pedir confirmación antes de acciones críticas
- Resolver ambigüedades por texto libre
- Funcionar con fallback por reglas si no hay LLM local disponible
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

Activa el polling del bot:

```bash
python main.py
```

Asegúrate de tener `RUN_TELEGRAM_BOT=true` en `.env`.

## Probar en Telegram

1. Abre el bot configurado en Telegram.
2. Envía `/start`.
3. Prueba con texto natural:
   - `programa reunion con ana manana a las 15:30`
   - `cancela reunion semanal`
   - `mueve la cita 3 a manana 18:00`
4. Responde `si`, `no` o el número de opción si el sistema pide desambiguación.

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
