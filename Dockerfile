FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Cloud instance runs in demo-only mode: live Tinder connections are refused
# (datacenter IPs get accounts flagged); live mode is localhost-only by design.
ENV PORT=8080
ENV ENV=cloud
CMD exec python -c "import uvicorn; import app; uvicorn.run(app.app, host='0.0.0.0', port=int(__import__('os').environ.get('PORT','8080')), log_level='warning')"
