# Railway-friendly build: includes ffmpeg/ffprobe for iOS conversion + codec verification
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps: ffmpeg includes ffprobe
RUN apt-get update \
  && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps into a local venv (start.sh defaults to .venv)
COPY requirements.txt ./
RUN python -m venv .venv \
  && . .venv/bin/activate \
  && pip install --no-cache-dir -r requirements.txt

# App sources
COPY . ./

RUN chmod +x start.sh

ENV PATH="/app/.venv/bin:$PATH"

CMD ["sh", "start.sh"]
