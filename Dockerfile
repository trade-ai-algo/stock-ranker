# Optional: containerized deployment for VPS / Oracle Free Tier / Raspberry Pi.
# Cron stays on the host; the container is invoked per run:
#   docker build -t daily-ranker .
#   docker run --rm -e ANTHROPIC_API_KEY -v $(pwd)/data:/app/data daily-ranker
#   docker run --rm -e ANTHROPIC_API_KEY -v $(pwd)/data:/app/data daily-ranker --eval
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["python", "main.py"]
