# Use official Playwright image (includes Python + Browsers + OS Dependencies)
# This is the "Nuclear Option" against missing browser errors.
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

# Set working directory
WORKDIR /app

# Copy dependency definition
COPY requirements.txt .

# Install Python dependencies
# Playwright is already in the image, but this ensures other libs (streamlit, etc.) are installed.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose Streamlit's default port
EXPOSE 8501

# Run the application
# --server.address=0.0.0.0 is required for Docker containers
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
