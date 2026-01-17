FROM python:3.11-slim

WORKDIR /app

# Install Chrome dependencies
RUN apt-get update && apt-get install -y \
    chromium-browser \
    chromium-driver \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Copy files
COPY requirements.txt .
COPY crypto_faucet_bot.py .
COPY faucet_config.json .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Run bot
CMD ["python", "crypto_faucet_bot.py", "--continuous", "--interval", "30"]
