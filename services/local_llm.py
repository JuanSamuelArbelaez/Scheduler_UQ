from __future__ import annotations

from dataclasses import dataclass
import json
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


class LocalOllamaClient:
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def is_configured(self) -> bool:
        return bool(self.model)

    def analyze(self, text: str, context: dict[str, Any] | None = None) -> LocalLlmDecision | None:
        if not self.is_configured():
            return None

        prompt = self._build_prompt(text, context or {})
        try:
            response = self._post_json("/api/generate", {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
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

        prompt = (
            "Clasifica la intencion de este texto para una agenda. "
            "Devuelve solo JSON valido con la forma {\"intent\":\"create|read|update|delete|preferences|unknown\"}. "
            f"Texto: {text}"
        )

        try:
            response = self._post_json(
                "/api/generate",
                {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                },
            )
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
            response = self._post_json("/api/tags", {})
        except (URLError, TimeoutError, ValueError):
            return None

        models_raw = response.get("models") if isinstance(response, dict) else None
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
            return False, "OLLAMA_MODEL no está configurado"

        models = self.list_models()
        if models is None:
            return False, "No se pudo conectar con Ollama"

        if self.model in models:
            return True, f"Ollama listo con modelo {self.model}"

        return False, (
            f"El modelo configurado '{self.model}' no está disponible en Ollama. "
            f"Modelos detectados: {', '.join(models) if models else 'ninguno'}"
        )

    def _build_prompt(self, text: str, context: dict[str, Any]) -> str:
        return (
            "Eres un asistente para una agenda. Devuelve JSON valido y solo JSON. "
            "Campos permitidos: action(create|update|cancel|read|preferences|unknown), title, start, end, description, "
            "event_id, title_query, needs_clarification, clarification. "
            "Usa fechas ISO 8601 cuando sea posible. Si la solicitud es ambigua, activa needs_clarification y pregunta de forma breve. "
            f"Contexto: {json.dumps(context, ensure_ascii=False)}. Texto: {text}"
        )

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=20) as response:
            raw_body = response.read().decode("utf-8")
        return json.loads(raw_body)


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
