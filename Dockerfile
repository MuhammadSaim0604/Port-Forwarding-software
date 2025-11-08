# Use official Python runtime as a parent image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable stdout/stderr unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements and install first (leverages Docker cache)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app

# Expose the default port (the app reads PORT from env at runtime)
EXPOSE 5000

# By default run the app using the existing entrypoint
CMD ["python", "app.py"]
