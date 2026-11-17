# Use the official Python slim image to keep the size small
FROM python:3.13-slim

# Install ffmpeg, which is strictly required by yt-dlp to process and stream audio
RUN apt-get update && \
    apt-get install -y ffmpeg curl unzip && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# yt-dlp hands YouTube's player challenge to an external JavaScript runtime
# (EJS). Deno is the only runtime it enables by default, and without one cloud
# hosts lose formats and get "Sign in to confirm you're not a bot".
# Pinned: yt-dlp requires Deno >= 2.3, and a floating tag would let a new Deno
# release silently change streaming behaviour on the next deploy.
ARG DENO_VERSION=2.9.8
RUN curl -fsSL https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip \
      -o /tmp/deno.zip && \
    unzip /tmp/deno.zip -d /usr/local/bin && \
    chmod +x /usr/local/bin/deno && \
    rm /tmp/deno.zip && \
    deno --version

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to take advantage of Docker caching
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend code into the container
COPY backend ./backend

# Prebuilt Expo web app, served by FastAPI at /
# (rebuild: cd VibeFmExpo && npx expo export --platform web --output-dir ../web)
COPY web ./web

# Change working directory to where the app code lives
WORKDIR /app/backend

# Render dynamically assigns a PORT environment variable.
# We use $PORT if it exists, otherwise we fallback to 8000.
CMD ["sh", "-c", "uvicorn app.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
