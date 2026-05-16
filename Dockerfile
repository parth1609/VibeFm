# Use the official Python slim image to keep the size small
FROM python:3.13-slim

# Install ffmpeg, which is strictly required by yt-dlp to process and stream audio
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to take advantage of Docker caching
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code into the container
COPY backend ./backend

# Change working directory to where the app code lives
WORKDIR /app/backend

# Render dynamically assigns a PORT environment variable.
# We use $PORT if it exists, otherwise we fallback to 8000.
CMD ["sh", "-c", "uvicorn app.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
