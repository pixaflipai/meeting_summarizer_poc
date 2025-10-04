FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY webhook_fastapi.py create_bot.py summarizer.py agent_factory.py llm_setup.py cache_manager.py ./

RUN mkdir -p /app/transcripts_projects /app/summary_cache

EXPOSE 8000

CMD ["uvicorn", "webhook_fastapi:app", "--host", "localhost", "--port", "8000"]