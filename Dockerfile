FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home app && mkdir -p /app/var /app/cache && chown -R app:app /app/var /app/cache
USER app
EXPOSE 8000
CMD ["uvicorn", "dashboard.app:api", "--host", "0.0.0.0", "--port", "8000"]
