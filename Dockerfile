FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH="."

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY app/backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY app /app/app
COPY models /app/models
COPY datasets /app/datasets
COPY training /app/training
COPY main.py /app/main.py

# Create logs directory
RUN mkdir -p /app/logs

# Expose port
EXPOSE 8000

# Start server
CMD ["python", "app/backend/main.py"]
