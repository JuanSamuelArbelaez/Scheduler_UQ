FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        ffmpeg \
        libsndfile1 \
        libespeak1 \
        espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

RUN python -m pip install --upgrade "pip<25" "setuptools<81" wheel \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch==2.4.1 torchaudio==2.4.1 \
    && pip config set global.extra-index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-build-isolation -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "main.py"]
