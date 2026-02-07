# Job Radar - Docker Image
# Supports both dashboard (Streamlit) and scanner (background service)

FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY dashboard/ ./dashboard/
COPY scripts/ ./scripts/

# Create directories for data and logs
RUN mkdir -p /app/logs /app/data

# Default environment variables
# DATABASE_URL is set by docker-compose (PostgreSQL) or .env (SQLite for local dev)
ENV DASHBOARD_PORT=8501

# Expose Streamlit port
EXPOSE 8501

# Default command (can be overridden in docker-compose)
CMD ["python", "src/main.py"]
