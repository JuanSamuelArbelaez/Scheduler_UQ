# AI_MODELS.md — Modelos de IA y Lógica de Agentes

## 1. Estado actual del runtime

El runtime del proyecto utiliza agentes de tipo **simbólico/regla** en Python.

No hay, por ahora, una llamada obligatoria a LLM externo para ejecutar CRUD de agenda.

Esto significa que:

* NLP Agent usa normalización y tokenización simple
* Intent Agent usa clasificación por palabras clave
* Priority Agent usa reglas por palabras de urgencia
* Confirmation Agent usa reglas de negocio para confirmar acciones críticas

### Proveedores y versiones en runtime

* Proveedor LLM remoto: ninguno
* Proveedor LLM local: ninguno por ahora
* Versión de modelo en runtime: no aplica, porque el flujo operativo actual no depende de un LLM

Todo el comportamiento productivo actual es local y determinístico.

## 2. Modelo usado para desarrollo asistido

Durante el desarrollo del código se usa un asistente de programación (GPT-5.3-Codex),
pero ese modelo **no forma parte del runtime de producción** del bot.

* Proveedor de desarrollo: OpenAI
* Modelo de desarrollo asistido: GPT-5.3-Codex
* Uso: generación y refactorización de código durante el desarrollo, no inferencia del bot en producción

## 3. Mapeo actual por agente

* Orchestrator Agent: lógica determinística de orquestación
* NLP Agent: normalización textual y parsing por reglas
* Intent Agent: heurísticas por keywords
* Scheduling Agent: validaciones de negocio y operación CRUD
* Priority Agent: scoring de prioridad por reglas
* Notification Agent: plantillas de lenguaje natural
* Confirmation Agent: política de confirmación explícita
* User Preferences Agent: persistencia de preferencias en SQLite
* History Agent: auditoría de acciones en SQLite

## 4. Evolución recomendada

Si se integra un LLM en runtime, se recomienda:

* agregar proveedor y versión en este archivo
* preferir un proveedor local cuando el caso de uso permita privacidad/offline
* separar prompts por agente
* agregar fallback determinístico ante timeout/errores
* versionar métricas de precisión del parser natural