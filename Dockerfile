# Use a secure, lightweight Python base image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000
ENV TZ=Asia/Manila

# Set the working directory inside the container
WORKDIR /app

# Install standard system libraries and configure timezone
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to optimize Docker cache layer
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application codebase
COPY . .

# Create a non-privileged user for enhanced container security
RUN adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app

# Switch to the non-privileged user
USER appuser

# Expose target port
EXPOSE 8000

# Command to execute the application using uvicorn
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
