# Scheduler UQ

Scheduler UQ is a local-first agenda assistant with:
- Flask web app with auth + OTP
- Natural language scheduling in Spanish
- Google Calendar sync via MCP
- Speech pipeline (STT + TTS)
- Ollama/Qwen support

## Current Architecture

The project runs in split services with Docker Compose:
- `web`: Flask UI/API (`:5000`)
- `mcp`: MCP bridge for Google Calendar (`:8088` internal)
- `speech`: STT/TTS HTTP service (`:8090` internal)
- `ollama`: local LLM runtime (`:11434` internal)

## Current State

- Telegram runtime flow removed.
- Web app is the main user channel.
- Calendar sync happens through MCP provider.
- Agenda listing excludes cancelled events.
- Cancellation no longer reverts event status after delete sync.
- TTS normalization improved for dates, times, and acronyms.

## New Setup (Clean Clone)

A new contributor will not have secrets or local DB by default.

Expected missing local files on first run:
- `.env` (must be created from `.env.example`)
- `credentials.json` (Google service account, optional depending on flow)
- `oauth_client_secret.json` (Google OAuth client)
- `scheduler.db` (created at runtime)

### 1) Configure environment

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### 2) Create Google JSON files from templates

- `credentials.example.json` -> `credentials.json`
- `oauth_client_secret.example.json` -> `oauth_client_secret.json`

Fill them with your Google Cloud credentials.

### 3) Start the stack

```bash
docker compose up -d --build
```

### 4) Open app

- http://127.0.0.1:5000

## Secrets and Docker

Secrets in `.env` are injected into containers as runtime environment variables.
They are not baked into images unless copied explicitly during image build.

Important:
- Do not commit `.env`, `credentials.json`, `oauth_client_secret.json`.
- Users with Docker host access can inspect container env values.
- For stricter security, use Docker secrets or an external secret manager.

## Tests

Automated suite:

```bash
python run_tests.py
```

Manual/integration script:
- `tests/manual/system_manual.py`

Recommendation:
- Keep tests, do not delete them.
- Keep fast unit tests in `tests/`.
- Keep long/manual scenarios in `tests/manual/`.
