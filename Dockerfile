# Use standard Python image (Avoids MCR registry 403 errors)
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies for Playwright (and general build tools)
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first
COPY requirements.txt .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Browsers (Chromium only to save space/time)
RUN playwright install --with-deps chromium

# Copy app code
COPY . .

# Hugging Face Spaces expects port 7860
EXPOSE 7860

# Run Streamlit on port 7860
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=7860"]
