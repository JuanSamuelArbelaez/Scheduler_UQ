# Scheduler UQ

Scheduler UQ es un asistente de agenda local-first con:
- Aplicación web Flask con autenticación + OTP
- Agendamiento por lenguaje natural en español
- Sincronización directa con Google Calendar
- Pipeline de voz (STT + TTS)
- Soporte para Ollama/Qwen

## Arquitectura Actual

El proyecto corre con servicios separados usando Docker Compose:
- `web`: Flask UI/API (`:5000`)
- `speech`: servicio HTTP de STT/TTS (`:8090` interno)
- `ollama`: runtime local del LLM (`:11434` interno)

## Estado Actual

- El flujo runtime de Telegram fue eliminado.
- La web es el canal principal de usuario.
- La sincronización de calendario ocurre mediante provider directo de Google Calendar.
- El listado de agenda excluye eventos cancelados.
- La cancelación ya no revierte el estado del evento tras el delete sync.
- La normalización de TTS mejoró para fechas, horas y siglas.

## Nuevo Setup (Clon Limpio)

Un nuevo colaborador no tendrá secretos ni base de datos local por defecto.

Archivos locales que normalmente faltan en el primer arranque:
- `.env` (debe crearse desde `.env.example`)
- `credentials.json` (service account de Google, opcional según el flujo)
- `oauth_client_secret.json` (cliente OAuth de Google)
- `scheduler.db` (se crea en runtime)

### 1) Configurar entorno

```bash
cp .env.example .env
```

En Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### 2) Crear archivos JSON de Google desde plantillas

- `credentials.example.json` -> `credentials.json`
- `oauth_client_secret.example.json` -> `oauth_client_secret.json`

Completa estos archivos con tus credenciales de Google Cloud.

### 3) Levantar el stack

```bash
docker compose up -d --build
```

### 4) Abrir la app

- http://127.0.0.1:5000

## Secretos y Docker

Los secretos en `.env` se inyectan a los contenedores como variables de entorno en runtime.
No quedan embebidos en las imágenes, salvo que se copien explícitamente durante el build.

Importante:
- No hagas commit de `.env`, `credentials.json`, `oauth_client_secret.json`.
- Usuarios con acceso al host de Docker pueden inspeccionar variables de entorno del contenedor.
- Para mayor seguridad, usa Docker secrets o un secret manager externo.

## Pruebas

Suite automatizada:

```bash
python run_tests.py
```

Script manual/de integración:
- `tests/manual/system_manual.py`

Recomendación:
- Mantén los tests, no los borres.
- Mantén los unit tests rápidos en `tests/`.
- Mantén escenarios largos/manuales en `tests/manual/`.
