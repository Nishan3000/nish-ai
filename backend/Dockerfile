# Nova AI backend
FROM python:3.12-slim

# Run as a non-root user (defence in depth)
RUN useradd --create-home --shell /usr/sbin/nologin nova
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
USER nova

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
