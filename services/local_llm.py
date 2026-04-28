from __future__ import annotations

from dataclasses import dataclass
import json
from datetime import datetime
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(slots=True)
class LocalLlmDecision:
    action: str
    title: str | None = None
    start: str | None = None
    end: str | None = None
    description: str | None = None
    event_id: int | None = None
    title_query: str | None = None
    needs_clarification: bool = False
    clarification: str | None = None


class QwenClient:
    """Cliente optimizado para Qwen 2.5 Instruct"""

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def is_configured(self) -> bool:
        return bool(self.model and "qwen" in self.model.lower())

    def analyze(self, text: str, context: dict[str, Any] | None = None) -> LocalLlmDecision | None:
        if not self.is_configured():
            return None

        prompt = self._build_analysis_prompt(text, context or {})
        try:
            response = self._post_json("/api/generate", {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    "num_predict": 512
                }
            })
        except (URLError, TimeoutError, ValueError):
            return None

        payload = response.get("response") if isinstance(response, dict) else None
        if not isinstance(payload, str):
            return None

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None

        if not isinstance(data, dict):
            return None

        return LocalLlmDecision(
            action=str(data.get("action") or "unknown"),
            title=_optional_str(data.get("title")),
            start=_optional_str(data.get("start")),
            end=_optional_str(data.get("end")),
            description=_optional_str(data.get("description")),
            event_id=_optional_int(data.get("event_id")),
            title_query=_optional_str(data.get("title_query")),
            needs_clarification=bool(data.get("needs_clarification", False)),
            clarification=_optional_str(data.get("clarification")),
        )

    def classify_intent(self, text: str) -> str | None:
        if not self.is_configured():
            return None

        prompt = self._build_intent_prompt(text)
        try:
            response = self._post_json("/api/generate", {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.0,
                    "top_p": 1.0,
                    "num_predict": 128
                }
            })
        except (URLError, TimeoutError, ValueError):
            return None

        payload = response.get("response") if isinstance(response, dict) else None
        if not isinstance(payload, str):
            return None

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None

        intent = data.get("intent") if isinstance(data, dict) else None
        if not isinstance(intent, str):
            return None
        return intent.strip().lower() or None

    def list_models(self) -> list[str] | None:
        try:
            with urlopen(f"{self.base_url}/api/tags", timeout=20) as response:
                raw_body = response.read().decode("utf-8")
            response_data = json.loads(raw_body)
        except (URLError, TimeoutError, ValueError):
            return None

        models_raw = response_data.get("models") if isinstance(response_data, dict) else None
        if not isinstance(models_raw, list):
            return []

        models: list[str] = []
        for item in models_raw:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name.strip():
                models.append(name.strip())
        return models

    def ensure_ready(self) -> tuple[bool, str]:
        if not self.is_configured():
            return False, "Qwen model not configured"

        models = self.list_models()
        if models is None:
            return False, "Cannot connect to Ollama"

        if self.model in models:
            return True, f"Qwen ready with model {self.model}"

        return False, (
            f"Configured model '{self.model}' not available in Ollama. "
            f"Available models: {', '.join(models) if models else 'none'}"
        )

    def _build_analysis_prompt(self, text: str, context: dict[str, Any]) -> str:
        """Prompt optimizado para Qwen 2.5 para análisis de agenda"""
        user_timezone = context.get("user_timezone", "America/Bogota")
        current_time = context.get("current_time", datetime.now().isoformat())

        return f"""<|im_start|>system
Eres un asistente inteligente para gestión de agendas en español. Tu tarea es analizar el texto del usuario y devolver una respuesta JSON estructurada.

INSTRUCCIONES:
- Analiza la intención del usuario sobre su agenda
- Extrae información temporal precisa en español
- Usa zona horaria: {user_timezone}
- Hora actual: {current_time}
- Si hay ambigüedad, pide aclaración breve
- Devuelve SOLO JSON válido, sin texto adicional

FORMATO DE RESPUESTA JSON:
{{
  "action": "create|update|cancel|read|preferences|unknown",
  "title": "título del evento (opcional)",
  "start": "fecha/hora inicio en ISO 8601 (opcional)",
  "end": "fecha/hora fin en ISO 8601 (opcional)",
  "description": "descripción (opcional)",
  "event_id": número ID (opcional),
  "title_query": "consulta por título (opcional)",
  "needs_clarification": true/false,
  "clarification": "mensaje de aclaración (opcional)"
}}

REGLAS TEMPORALES:
- "hoy" = fecha actual
- "mañana" = fecha actual + 1 día
- "pasado mañana" = fecha actual + 2 días
- Días de semana: lunes, martes, etc. (próximo si ya pasó)
- Horas: 3pm = 15:00, 7:30 am = 07:30
- Fechas: 20/04/2026, 2026-04-20
- Si no se especifica duración, usar 1 hora por defecto

EJEMPLOS:
"Agenda reunión mañana a las 3pm" -> {{"action":"create","title":"reunión","start":"2026-04-21T15:00:00","end":"2026-04-21T16:00:00"}}
"¿Qué tengo hoy?" -> {{"action":"read"}}
"Mueve la reunión a las 5pm" -> {{"action":"update","title_query":"reunión","start":"2026-04-21T17:00:00"}}
<|im_end|>
<|im_start|>user
Texto del usuario: {text}

Contexto adicional: {json.dumps(context, ensure_ascii=False)}
<|im_end|>
<|im_start|>assistant
"""

    def _build_intent_prompt(self, text: str) -> str:
        """Prompt optimizado para clasificación de intención con Qwen"""
        return f"""<|im_start|>system
Clasifica la intención del siguiente texto relacionado con una agenda.

Devuelve SOLO JSON con el formato exacto:
{{"intent": "create|read|update|delete|preferences|unknown"}}

INTENCIONES:
- create: crear/agendar nueva cita
- read: consultar/ver agenda
- update: modificar cita existente
- delete: cancelar/eliminar cita
- preferences: configurar email/zona horaria
- unknown: no clasificable

EJEMPLOS:
"Agenda reunión mañana" -> {{"intent": "create"}}
"¿Qué citas tengo?" -> {{"intent": "read"}}
"Cambia la hora de la reunión" -> {{"intent": "update"}}
<|im_end|>
<|im_start|>user
Texto: {text}
<|im_end|>
<|im_start|>assistant
"""

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            raw_body = response.read().decode("utf-8")
        return json.loads(raw_body)


# Alias para compatibilidad
LocalOllamaClient = QwenClient


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
