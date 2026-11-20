FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
  && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv==0.13.9

COPY pyproject.toml uv.lock /app/
COPY apps/api /app/apps/api
COPY data/demo /app/data/demo
RUN uv sync --frozen --no-dev --project apps/api

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/apps/api/src

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
