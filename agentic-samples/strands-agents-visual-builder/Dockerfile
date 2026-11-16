FROM --platform=linux/amd64 python:3.13.7-slim

ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    git \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# install nvm
RUN curl -fsSL https://deb.nodesource.com/setup_23.x -o-  | bash && apt-get install -y nodejs  && node -v && npm -v && npx -v 

RUN python -m pip install uv

RUN npm install -g npm


# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create instance directory if it doesn't exist
RUN mkdir -p instance

# Drop root before starting the application. The application only needs to
# write its local SQLite database and temporary runtime files.
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --create-home --home-dir /home/appuser appuser \
    && chown -R appuser:appuser /app /home/appuser
USER appuser

# Expose port
EXPOSE 5000


# Run the application
ENTRYPOINT ["gunicorn", "app:app",     "--bind", "0.0.0.0:5000",     "--workers", "2",     "--preload",     "-k", "uvicorn.workers.UvicornWorker"]
