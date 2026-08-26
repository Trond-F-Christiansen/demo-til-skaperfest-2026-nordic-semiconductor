FROM python:3.13-slim

WORKDIR /app

COPY backend /app/backend
COPY site /app/site

ENV PYTHONUNBUFFERED=1
ENV WEBSITE_OUTPUT_DIR=/data

EXPOSE 8000

CMD ["python3", "/app/backend/mqtt_listener.py"]
