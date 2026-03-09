# Use an official lightweight Python image
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y build-essential libpq-dev --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# install python deps
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# copy project
COPY . .

# collect static (will run during image build)
RUN python manage.py collectstatic --noinput || true

EXPOSE 8000

# Use gunicorn for production
CMD ["gunicorn", "IntelliHub.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
