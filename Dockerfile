FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY index.html server.py ./
RUN mkdir -p /app/media

ENV HOST=0.0.0.0 PORT=10000 ALLOWED_ORIGINS=*
EXPOSE 10000
CMD ["python", "server.py"]
