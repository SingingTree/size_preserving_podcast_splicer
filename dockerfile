FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y \
    ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m appuser

# Copy project files and dependencies first
COPY pyproject.toml README.md ./
COPY app ./app

# Install dependencies with uv using pyproject.toml
RUN pip install --no-cache-dir uv && \
    uv pip install --no-cache --system .

# Now copy media and static files
COPY media/ ./media/
COPY static/ ./static/

# Set ownership of all files
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]