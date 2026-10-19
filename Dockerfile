FROM public.ecr.aws/docker/library/python:3.11-slim@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-agent.txt requirements-agent.lock.txt ./
RUN python -m pip install --no-cache-dir -r requirements-agent.txt -r requirements-agent.lock.txt
COPY app/ ./app/
COPY data/documents/ ./data/documents/
COPY evaluation/week2/corpus_manifest.csv ./evaluation/week2/corpus_manifest.csv
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.agent_api:app", "--host", "0.0.0.0", "--port", "8000"]
