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
        self.provider = (provider or "coqui").strip().lower()
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
        cleaned = self._expand_structured_tokens(cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _expand_structured_tokens(self, text: str) -> str:
        month_names = {
            1: "enero",
            2: "febrero",
            3: "marzo",
            4: "abril",
            5: "mayo",
            6: "junio",
            7: "julio",
            8: "agosto",
            9: "septiembre",
            10: "octubre",
            11: "noviembre",
            12: "diciembre",
        }

        def replace_date(match: re.Match[str]) -> str:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            month_label = month_names.get(month)
            if month_label is None:
                return match.group(0)
            return (
                f"{self._number_to_words_es(day)} de {month_label} "
                f"de {self._number_to_words_es(year)}"
            )

        def replace_time(match: re.Match[str]) -> str:
            hour = int(match.group(1))
            minute = int(match.group(2))
            hour_12 = hour % 12
            if hour_12 == 0:
                hour_12 = 12
            if hour < 12:
                period = "de la manana"
            elif hour < 19:
                period = "de la tarde"
            else:
                period = "de la noche"

            hour_label = self._number_to_words_es(hour_12)
            if minute == 0:
                return f"{hour_label} {period}"
            minute_label = self._number_to_words_es(minute)
            return f"{hour_label} y {minute_label} {period}"

        def replace_acronym(match: re.Match[str]) -> str:
            token = match.group(0)
            return " ".join(self._letter_name_es(char) for char in token)

        def replace_plain_number(match: re.Match[str]) -> str:
            value = int(match.group(0))
            return self._number_to_words_es(value)

        expanded = re.sub(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", replace_date, text)
        expanded = re.sub(r"\b(\d{1,2}):(\d{2})\b", replace_time, expanded)
        expanded = re.sub(r"\b[A-Z]{2,5}\b", replace_acronym, expanded)
        expanded = re.sub(r"\b\d{1,4}\b", replace_plain_number, expanded)
        return expanded

    def _letter_name_es(self, char: str) -> str:
        names = {
            "A": "a",
            "B": "be",
            "C": "ce",
            "D": "de",
            "E": "e",
            "F": "efe",
            "G": "ge",
            "H": "hache",
            "I": "i",
            "J": "jota",
            "K": "ka",
            "L": "ele",
            "M": "eme",
            "N": "ene",
            "O": "o",
            "P": "pe",
            "Q": "cu",
            "R": "erre",
            "S": "ese",
            "T": "te",
            "U": "u",
            "V": "uve",
            "W": "doble u",
            "X": "equis",
            "Y": "ye",
            "Z": "zeta",
        }
        return names.get(char.upper(), char.lower())

    def _number_to_words_es(self, number: int) -> str:
        if number < 0:
            return f"menos {self._number_to_words_es(abs(number))}"

        units = [
            "cero",
            "uno",
            "dos",
            "tres",
            "cuatro",
            "cinco",
            "seis",
            "siete",
            "ocho",
            "nueve",
        ]

        special = {
            10: "diez",
            11: "once",
            12: "doce",
            13: "trece",
            14: "catorce",
            15: "quince",
            16: "dieciseis",
            17: "diecisiete",
            18: "dieciocho",
            19: "diecinueve",
            20: "veinte",
            21: "veintiuno",
            22: "veintidos",
            23: "veintitres",
            24: "veinticuatro",
            25: "veinticinco",
            26: "veintiseis",
            27: "veintisiete",
            28: "veintiocho",
            29: "veintinueve",
        }

        tens_names = {
            30: "treinta",
            40: "cuarenta",
            50: "cincuenta",
            60: "sesenta",
            70: "setenta",
            80: "ochenta",
            90: "noventa",
        }

        hundreds_names = {
            100: "cien",
            200: "doscientos",
            300: "trescientos",
            400: "cuatrocientos",
            500: "quinientos",
            600: "seiscientos",
            700: "setecientos",
            800: "ochocientos",
            900: "novecientos",
        }

        if number < 10:
            return units[number]
        if number in special:
            return special[number]
        if number < 100:
            tens = (number // 10) * 10
            remainder = number % 10
            if remainder == 0:
                return tens_names.get(tens, str(number))
            return f"{tens_names.get(tens, str(tens))} y {units[remainder]}"
        if number < 1000:
            if number in hundreds_names:
                return hundreds_names[number]
            hundreds = (number // 100) * 100
            remainder = number % 100
            if hundreds == 100:
                return f"ciento {self._number_to_words_es(remainder)}"
            return f"{hundreds_names.get(hundreds, str(hundreds))} {self._number_to_words_es(remainder)}"
        if number < 1_000_000:
            thousands = number // 1000
            remainder = number % 1000
            prefix = "mil" if thousands == 1 else f"{self._number_to_words_es(thousands)} mil"
            if remainder == 0:
                return prefix
            return f"{prefix} {self._number_to_words_es(remainder)}"

        return str(number)

    def _ensure_model(self) -> None:
        if self._tts is not None or self._import_error is not None:
            return

        with self._lock:
            if self._tts is not None or self._import_error is not None:
                return

            load_order: list[str]
            if self.provider == "pyttsx3":
                load_order = ["pyttsx3"]
            elif self.provider == "coqui":
                load_order = ["coqui", "pyttsx3"]
            else:
                load_order = ["coqui", "pyttsx3"]

            errors: list[str] = []
            for backend in load_order:
                if backend == "coqui":
                    try:
                        tts_api_module = importlib.import_module("TTS.api")
                        tts_class = getattr(tts_api_module, "TTS")
                        self._tts = tts_class(model_name=self.model_name, progress_bar=False)
                        self._backend = "coqui"
                        return
                    except Exception as error:
                        errors.append(f"coqui: {error}")
                        continue

                if backend == "pyttsx3":
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
                        return
                    except Exception as error:
                        errors.append(f"pyttsx3: {error}")
                        continue

            error_detail = "; ".join(errors) if errors else "sin detalle"
            self._import_error = (
                f"No fue posible cargar TTS local (provider={self.provider}, model={self.model_name}): "
                f"{error_detail}"
            )

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
