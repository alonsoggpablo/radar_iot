FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY aglabs_radar_bridge.py .

RUN mkdir -p /var/lib/radar_iot

CMD ["python", "-u", "aglabs_radar_bridge.py"]
