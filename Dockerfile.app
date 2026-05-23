FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.app.txt ./requirements.app.txt

RUN python -m pip install --upgrade "pip<25" "setuptools<81" wheel \
    && pip install -r requirements.app.txt

COPY . .

EXPOSE 5000

CMD ["python", "main.py"]