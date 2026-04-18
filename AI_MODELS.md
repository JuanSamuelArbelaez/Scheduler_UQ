# AI_MODELS.md — Modelos de IA y Lógica de Agentes

## 1. Estado actual del runtime

El runtime del proyecto utiliza un enfoque **híbrido**:

* clasificación de intención con LLM local (cuando `LLM_PROVIDER=ollama`)
* fallback determinístico por reglas para mantener resiliencia

No hay llamada obligatoria a proveedor remoto.

El proyecto usa LLM local vía Ollama para:

* extraer fechas y horas en lenguaje natural
* resolver ambigüedad en títulos de eventos
* proponer preguntas de aclaración cuando faltan datos

Esto significa que:

* NLP Agent usa normalización y tokenización simple
* Intent Agent usa LLM primero y fallback por palabras clave si el LLM falla o devuelve `unknown`
* Priority Agent usa reglas por palabras de urgencia
* Confirmation Agent usa reglas de negocio para confirmar acciones críticas

### Proveedores y versiones en runtime

* Proveedor LLM remoto: ninguno
* Proveedor LLM local opcional: Ollama
* Versión de modelo local: configurable por `OLLAMA_MODEL`
* Modelos sugeridos: `llama3.1:8b`, `qwen2.5:7b-instruct`, `mistral:7b-instruct`

Si `LLM_PROVIDER=ollama` y `OLLAMA_MODEL` está definido, el arranque del bot valida que Ollama esté disponible y que el modelo exista antes de iniciar polling.
Si esa validación falla, el bot no inicia para evitar inconsistencias en clasificación.

Si `LLM_PROVIDER` no es `ollama`, el sistema funciona solo con lógica determinística.

## 2. Modelo usado para desarrollo asistido

Durante el desarrollo del código se usa un asistente de programación (GPT-5.3-Codex),
pero ese modelo **no forma parte del runtime de producción** del bot.

* Proveedor de desarrollo: OpenAI
* Modelo de desarrollo asistido: GPT-5.3-Codex
* Uso: generación y refactorización de código durante el desarrollo, no inferencia del bot en producción

## 3. Mapeo actual por agente

* Orchestrator Agent: lógica determinística de orquestación
* NLP Agent: normalización textual y parsing por reglas
* Intent Agent: LLM local por defecto (si está habilitado) + heurísticas por keywords como fallback
* Scheduling Agent: validaciones de negocio y operación CRUD
* Priority Agent: scoring de prioridad por reglas
* Notification Agent: plantillas de lenguaje natural
* Confirmation Agent: política de confirmación explícita
* User Preferences Agent: persistencia de preferencias en SQLite
* History Agent: auditoría de acciones en SQLite

## 4. Evolución recomendada

Si se integra un LLM en runtime, se recomienda:

* preferir un proveedor local cuando el caso de uso permita privacidad/offline
* separar prompts por agente
* agregar fallback determinístico ante timeout/errores
* versionar métricas de precisión del parser natural