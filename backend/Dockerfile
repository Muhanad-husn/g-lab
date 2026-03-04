FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files and install
COPY pyproject.toml .
COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/

RUN pip install --no-cache-dir .

# Create data directory
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
