from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile

from flask import Flask, jsonify, request, send_file

from services.speech_to_text_service import SpeechToTextService
from services.text_to_speech_service import TextToSpeechService


def create_app() -> Flask:
    app = Flask(__name__)

    whisper_model = os.getenv("WHISPER_MODEL", "base").strip() or "base"
    tts_provider = os.getenv("TTS_PROVIDER", "coqui").strip().lower() or "coqui"
    tts_model_name = os.getenv("TTS_MODEL_NAME", "tts_models/es/css10/vits").strip() or "tts_models/es/css10/vits"

    stt_service = SpeechToTextService(model_name=whisper_model)
    tts_service = TextToSpeechService(provider=tts_provider, model_name=tts_model_name)

    @app.get("/health")
    def health() -> tuple[dict[str, object], int]:
        return {"ok": True, "ready": True}, 200

    @app.get("/ready")
    def ready() -> tuple[dict[str, object], int]:
        return {
            "ok": True,
            "stt_available": stt_service.is_available(),
            "tts_available": tts_service.is_available(),
        }, 200

    @app.post("/stt")
    def stt() -> tuple[dict[str, object], int]:
        raw_audio = request.get_data(cache=False)
        if not raw_audio:
            return {"ok": False, "message": "Audio vacío"}, 400

        temp_path = ""
        try:
            with NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                handle.write(raw_audio)
                temp_path = handle.name

            text = stt_service.transcribe(Path(temp_path))
            return {"ok": True, "text": text}, 200
        except Exception as error:
            return {"ok": False, "message": str(error)}, 500
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    @app.post("/tts")
    def tts():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text") or "").strip()
        if not text:
            return jsonify({"ok": False, "message": "Texto vacío"}), 400

        try:
            wav_bytes = tts_service.synthesize(text)
        except Exception as error:
            return jsonify({"ok": False, "message": str(error)}), 500

        return send_file(BytesIO(wav_bytes), mimetype="audio/wav", as_attachment=False, download_name="reply.wav")

    return app


def main() -> None:
    app = create_app()
    host = os.getenv("SPEECH_HOST", "0.0.0.0")
    port = int(os.getenv("SPEECH_PORT", "8090"))
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()
