FROM python:3.11-slim

WORKDIR /app

# Copy requirements first (for better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire application
COPY . .

# Verify templates folder exists (debug step)
RUN ls -la /app/templates || echo "Warning: templates folder not found"

EXPOSE 8080

# Old
# CMD ["gunicorn", ... "--workers", "2", ... "app:app"]

# New (Use 1 worker to keep a single in-memory history)
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]