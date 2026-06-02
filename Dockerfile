FROM python:3.12-slim
WORKDIR /code

# Установка зависимостей
RUN pip install --no-cache-dir fastapi uvicorn requests langchain-core langchain-community qdrant-client langchain-qdrant langchain-ollama

# Копируем всё содержимое текущей папки хоста (включая main.py) прямо в /code
COPY . /code/

# Запускаем uvicorn напрямую из корня. 
# Если main.py лежит в корне, имя модуля будет просто "main:app"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
