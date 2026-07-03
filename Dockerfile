# Production Dockerfile for Agent Grey - Docker Hub releases
# Multi-stage build optimized for pre-built images
# Stage 1: Base dependencies
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

WORKDIR /app

# Install system dependencies and configure timezone
# Security: apt-get upgrade ensures all system packages are patched
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    build-essential \
    postgresql-client \
    libpq-dev \
    # WeasyPrint dependencies for PDF generation
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libglib2.0-0 \
    libcairo2 \
    libcairo-gobject2 \
    libpangocairo-1.0-0 \
    gir1.2-pango-1.0 \
    # Health check tools
    curl \
    procps \
    tzdata \
    && rm -rf /var/lib/apt/lists/* \
    # Set timezone to UTC
    && ln -sf /usr/share/zoneinfo/UTC /etc/localtime \
    && echo "UTC" > /etc/timezone \
    && dpkg-reconfigure -f noninteractive tzdata

# Stage 2: Frontend build
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
# Copy Django templates so Tailwind @source directives can scan them
# Paths in django.css: ../../../../templates/ resolves to /app/templates/ from WORKDIR /app/frontend
COPY templates/ /app/templates/
COPY apps/ /app/apps/
RUN npx vite build

# Stage 3: Production environment
FROM base AS production

# Copy requirements for production
COPY requirements/base.txt requirements/production.txt ./

# Install production dependencies
RUN pip install --no-cache-dir -r production.txt

# Copy project
COPY . .

# Copy frontend build output (generated in frontend stage)
COPY --from=frontend /app/static/dist /app/static/dist

# Ensure scripts are executable (includes Phase 1 refactored utilities)
RUN chmod +x /app/scripts/*.sh /app/scripts/lib/*.py 2>/dev/null || true

# Production settings for collectstatic
ENV DJANGO_SETTINGS_MODULE=grey_lit_project.settings.production
ENV SECRET_KEY="dummy-key-for-collectstatic-only"
ENV DATABASE_URL="sqlite:///db.sqlite3"
ENV STATIC_URL="/static/"
ENV STATIC_ROOT="/app/staticfiles"

# Pre-create staticfiles directory and collect static files
RUN mkdir -p /app/staticfiles && \
    python manage.py collectstatic --noinput -v 0

# Create cache table for database cache fallback (idempotent operation)
RUN python manage.py createcachetable || true

# Unset build-time DATABASE_URL so runtime environment can set it
ENV DATABASE_URL=""

# Create non-root user for production
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app && \
    mkdir -p /app/media && \
    chown -R appuser:appuser /app/staticfiles /app/media

# Make startup script executable
COPY docker/startup.sh /app/startup.sh
RUN chmod +x /app/startup.sh && chown appuser:appuser /app/startup.sh

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=60s --timeout=15s --start-period=300s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/health/', timeout=10)" || exit 1

CMD ["/app/startup.sh"]
