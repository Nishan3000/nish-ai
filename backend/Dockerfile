# NISH backend
FROM python:3.12-slim

# Run as a non-root user (defence in depth)
RUN useradd --create-home --shell /usr/sbin/nologin nish
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
USER nish

EXPOSE 8000
# Apply migrations, then serve.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
