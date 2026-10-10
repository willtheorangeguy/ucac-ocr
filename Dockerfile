FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DATA_DIR=/data
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY app ./app
RUN useradd --uid 10001 --create-home pool && mkdir /data && chown pool /data
USER pool
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
