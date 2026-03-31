FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl && rm -rf /var/lib/apt/lists/*

# Copy platform
COPY evez-platform/ /app/evez-platform/
COPY SOUL.md MEMORY.md IDENTITY.md USER.md /app/

# Install Python deps
RUN pip install --no-cache-dir -r /evez-platform/requirements.txt

# Expose port
EXPOSE 8080

# Environment
ENV EVEZ_PORT=8080
ENV EVEZ_DATA=/app/data

# Run
CMD ["python3", "evez-platform/main.py"]
