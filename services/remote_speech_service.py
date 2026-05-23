from __future__ import annotations

import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RemoteSpeechToTextService:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            with urlopen(f"{self.base_url}/health", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return bool(payload.get("ok"))
        except Exception:
            return False

    def transcribe(self, audio_path: Path) -> str:
        data = audio_path.read_bytes()
        request = Request(
            f"{self.base_url}/stt",
            data=data,
            headers={"Content-Type": "audio/wav"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="ignore")
            raise RuntimeError(detail or f"STT request failed with HTTP {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"Speech service unreachable: {error}") from error

        text = str(payload.get("text") or "").strip()
        if not text:
            raise RuntimeError(str(payload.get("message") or "STT service returned empty text"))
        return text


class RemoteTextToSpeechService:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def is_available(self) -> bool:
        try:
            with urlopen(f"{self.base_url}/health", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            return bool(payload.get("ok"))
        except Exception:
            return False

    def synthesize(self, text: str) -> bytes:
        request = Request(
            f"{self.base_url}/tts",
            data=json.dumps({"text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                return response.read()
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="ignore")
            raise RuntimeError(detail or f"TTS request failed with HTTP {error.code}") from error
        except URLError as error:
            raise RuntimeError(f"Speech service unreachable: {error}") from error
