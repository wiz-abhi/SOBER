# SOBER live app — Hugging Face Spaces (Docker SDK) / Render / any container host.
# Serves captured golden JSON; no Cognee or LLM key needed at runtime.
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PORT=7860

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY web ./web
COPY golden ./golden

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
