# Use standard Python 3.9 image (Debian-based, contains common libs)
FROM python:3.9

# Set working directory
WORKDIR /app

# Install system dependencies manually (More reliable than --with-deps)
# These are the standard deps for Chromium on Debian
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python deps
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright (Browsers only, deps already installed manually)
RUN playwright install chromium

# Copy app code
COPY . .

# Expose generic port
EXPOSE 7860

# Run Streamlit on 7860
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=7860"]
