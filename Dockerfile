FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY alembic.ini .
COPY alembic/ alembic/
COPY prompts/ prompts/
COPY openclaw/ openclaw/
COPY skills/ skills/
COPY scripts/ scripts/
COPY src/ src/
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "agentropolis"]
