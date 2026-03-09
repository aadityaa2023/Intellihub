
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Default runtime envs
ENV PORT=8000
ENV WEB_CONCURRENCY=3

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y build-essential libpq-dev --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# install python deps
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# copy project
COPY . .

# collect static (fail build if collection fails)
RUN python manage.py collectstatic --noinput

# create a non-root user and give ownership to the app directory
RUN adduser --disabled-password --gecos '' app \
    && chown -R app:app /app

USER app

EXPOSE 8000

# Use gunicorn for production; allow `PORT`/`WEB_CONCURRENCY` to be set at deploy time
CMD ["sh", "-c", "gunicorn IntelliHub.wsgi:application --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY}"]
