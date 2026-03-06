FROM python:3.12-slim

WORKDIR /app

# Copy project files and install
COPY pyproject.toml .
COPY alembic.ini .
COPY alembic/ alembic/
COPY app/ app/

# Install with document extras; force CPU-only PyTorch to save ~500MB
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cpu \
    ".[documents]"

# Create data directory
RUN mkdir -p /data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
