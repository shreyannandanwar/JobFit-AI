FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (for PyPDF2 and potential future ML libs)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies first for better caching
COPY requirements.txt .

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application
COPY . .

# Create a volume for the SQLite DB to persist across restarts
VOLUME ["/app/data"]

# Expose the FastAPI port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV OPENAI_BASE_URL="https://api.openai.com/v1"

# Run the FastAPI server with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]