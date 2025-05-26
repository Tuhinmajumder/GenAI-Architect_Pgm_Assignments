FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN apt-get update && apt-get install -y git
RUN mkdir -p /tmp/clone_folder && chmod 777 /tmp/clone_folder
COPY backend/ .
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["python","-m","uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
