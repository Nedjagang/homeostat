FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default: run the batch claims demo. The control API overrides this (see docker-compose.yaml).
CMD ["python", "agent.py"]
