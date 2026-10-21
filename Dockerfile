# GenoTrack Serving Container
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source, crop configurations, pipeline orchestration, and web dashboard
COPY src/ ./src/
COPY crops/ ./crops/
COPY pipelines/ ./pipelines/
COPY monitoring/ ./monitoring/
COPY data/models/ ./data/models/
COPY data/processed/ ./data/processed/
COPY index.html ./index.html

EXPOSE 8000

CMD ["uvicorn", "src.serve.app:app", "--host", "0.0.0.0", "--port", "8000"]
