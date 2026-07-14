FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Foundry Hosted Agent platform expects port 8088
EXPOSE 8088
CMD ["python", "app_server.py"]
