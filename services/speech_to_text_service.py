from __future__ import annotations

import importlib
from pathlib import Path
from threading import Lock
from typing import Any


class SpeechToTextService:
    def __init__(self, model_name: str = "base") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._backend: str | None = None
        self._lock = Lock()
        self._import_error: str | None = None

    def is_available(self) -> bool:
        self._ensure_model()
        return self._model is not None

    def transcribe(self, audio_path: Path) -> str:
        self._ensure_model()
        if self._model is None:
            raise RuntimeError(self._import_error or "Whisper no está disponible en este entorno.")

        if self._backend == "openai-whisper":
            result = self._model.transcribe(str(audio_path), language="es")
            text = str(result.get("text") or "").strip()
        elif self._backend == "faster-whisper":
            segments, _info = self._model.transcribe(str(audio_path), language="es")
            text = " ".join(segment.text for segment in segments).strip()
        else:
            raise RuntimeError("Backend STT no soportado")

        if not text:
            raise ValueError("No se pudo extraer texto del audio.")
        return text

    def _ensure_model(self) -> None:
        if self._model is not None or self._import_error is not None:
            return

        with self._lock:
            if self._model is not None or self._import_error is not None:
                return
            try:
                whisper_module = importlib.import_module("whisper")
                self._model = whisper_module.load_model(self.model_name)
                self._backend = "openai-whisper"
            except Exception:
                try:
                    faster_whisper_module = importlib.import_module("faster_whisper")
                    whisper_model_cls = getattr(faster_whisper_module, "WhisperModel")
                    self._model = whisper_model_cls(self.model_name, device="cpu")
                    self._backend = "faster-whisper"
                except Exception as error:
                    self._import_error = (
                        f"No fue posible cargar Whisper ({self.model_name}) ni faster-whisper: {error}"
                    )
