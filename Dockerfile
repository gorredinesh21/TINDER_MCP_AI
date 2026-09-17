FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
ENV HOST=0.0.0.0
CMD exec python -c "import uvicorn; import app; uvicorn.run(app.app, host='0.0.0.0', port=int(__import__('os').environ.get('PORT','8080')), log_level='warning')"
