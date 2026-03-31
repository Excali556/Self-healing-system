FROM python:3.10-slim

WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of code
COPY . .

CMD ["python", "healer.py"]