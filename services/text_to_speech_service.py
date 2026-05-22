from __future__ import annotations

import importlib
from io import BytesIO
import os
import re
from tempfile import NamedTemporaryFile
from threading import Lock
import time


class TextToSpeechService:
    def __init__(self, provider: str = "coqui", model_name: str = "tts_models/es/css10/vits") -> None:
        self.provider = provider
        self.model_name = model_name
        self._tts = None
        self._backend: str | None = None
        self._lock = Lock()
        self._import_error: str | None = None
        self._spanish_voice_ready = False

    def is_available(self) -> bool:
        self._ensure_model()
        return self._tts is not None

    def synthesize(self, text: str) -> bytes:
        clean_text = self._sanitize_text_for_tts(text)
        if not clean_text:
            raise ValueError("No hay texto para sintetizar")

        self._ensure_model()
        if self._tts is None:
            raise RuntimeError(self._import_error or "TTS no disponible")
        if self._backend == "pyttsx3" and not self._spanish_voice_ready:
            raise RuntimeError(
                "No hay una voz en español instalada en Windows. "
                "Instala una voz ES-ES/ES-MX en Configuración > Hora e idioma > Voz."
            )

        temp_path = ""
        with NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            temp_path = handle.name

        try:
            if self._backend == "coqui":
                self._tts.tts_to_file(text=clean_text, file_path=temp_path)
            elif self._backend == "pyttsx3":
                self._tts.save_to_file(clean_text, temp_path)
                self._tts.runAndWait()
                # On some Windows environments, the engine flushes the WAV a bit later.
                deadline = time.time() + 3.0
                while time.time() < deadline:
                    if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                        break
                    time.sleep(0.1)
            else:
                raise RuntimeError("Backend TTS no soportado")

            with open(temp_path, "rb") as handle:
                data = handle.read()
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        if not data:
            raise RuntimeError("No se pudo generar audio TTS")

        buffer = BytesIO(data)
        return buffer.getvalue()

    def _sanitize_text_for_tts(self, text: str) -> str:
        cleaned = (text or "").replace("\n", " ").strip()
        cleaned = re.sub(r"[\u200d\ufe0f]", "", cleaned)

        emoji_ranges = (
            "\U0001f1e6-\U0001f1ff"
            "\U0001f300-\U0001f5ff"
            "\U0001f600-\U0001f64f"
            "\U0001f680-\U0001f6ff"
            "\U0001f700-\U0001f77f"
            "\U0001f780-\U0001f7ff"
            "\U0001f800-\U0001f8ff"
            "\U0001f900-\U0001f9ff"
            "\U0001fa00-\U0001faff"
            "\U00002700-\U000027bf"
            "\U00002600-\U000026ff"
        )
        cleaned = re.sub(f"[{emoji_ranges}]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _ensure_model(self) -> None:
        if self._tts is not None or self._import_error is not None:
            return

        with self._lock:
            if self._tts is not None or self._import_error is not None:
                return
            try:
                tts_api_module = importlib.import_module("TTS.api")
                tts_class = getattr(tts_api_module, "TTS")
                self._tts = tts_class(model_name=self.model_name, progress_bar=False)
                self._backend = "coqui"
            except Exception:
                try:
                    pyttsx3_module = importlib.import_module("pyttsx3")
                    engine = pyttsx3_module.init()
                    selected_voice_id = self._select_best_spanish_voice(engine.getProperty("voices"))
                    if selected_voice_id:
                        engine.setProperty("voice", selected_voice_id)
                        self._spanish_voice_ready = True
                    else:
                        self._spanish_voice_ready = False
                    self._tts = engine
                    self._backend = "pyttsx3"
                except Exception as error:
                    self._import_error = f"No fue posible cargar TTS local ({self.model_name}): {error}"

    def _select_best_spanish_voice(self, voices: list[object]) -> str | None:
        best_score = -1
        best_id: str | None = None

        for voice in voices:
            score = self._score_voice_for_spanish(voice)
            if score > best_score:
                best_score = score
                best_id = getattr(voice, "id", None)

        # Only apply explicit selection when there is positive evidence of Spanish support.
        if best_score <= 0:
            return None
        return best_id

    def _score_voice_for_spanish(self, voice: object) -> int:
        score = 0

        voice_name = (getattr(voice, "name", "") or "").lower()
        voice_id = (getattr(voice, "id", "") or "").lower()
        voice_langs = getattr(voice, "languages", []) or []

        spanish_keywords = (
            "spanish",
            "espanol",
            "espa\u00f1ol",
            "castilian",
            "castellano",
            "helena",
            "laura",
            "pablo",
            "sabina",
            "dalia",
            "sofia",
            "maria",
            "elvira",
            "es-mx",
            "es-es",
            "es-us",
        )

        for keyword in spanish_keywords:
            if keyword in voice_name:
                score += 3
            if keyword in voice_id:
                score += 3

        for lang in voice_langs:
            normalized = ""
            if isinstance(lang, bytes):
                try:
                    normalized = lang.decode("utf-8", errors="ignore").lower()
                except Exception:
                    normalized = ""
            else:
                normalized = str(lang).lower()

            if "es" in normalized:
                score += 5
            if "spanish" in normalized or "espanol" in normalized or "espa\u00f1ol" in normalized:
                score += 5

        return score
