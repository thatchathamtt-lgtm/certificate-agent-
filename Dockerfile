FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
EXPOSE 8080

# Cloud Run sets $PORT; gunicorn binds to it. 1 worker is plenty since
# Cloud Scheduler calls this at most once every few minutes.
CMD exec gunicorn --bind :$PORT --workers 1 --timeout 300 main:app
