# Точка входа FastAPI, оркестрация

import os
import re
import requests
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

# Актуальные и правильные импорты под свежие версии LangChain (2026 год)
from langchain_ollama import ChatOllama
from langchain_ollama import OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
#from langchain_qdrant import Qdrant
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

app = FastAPI(
    title="ITSM AI Integration Gateway",
    description="Компонент MVP для синхронной интеграции GLPI, Qdrant и Ollama"
)

# ==========================================
# 1. КОНФИГУРАЦИЯ ИНФРАСТРУКТУРЫ (СТЕНД ВКР)
# ==========================================
# Базовый URL для локальной Ollama (ВМ 2)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.222.66:11434")

# ВМ 3: Портал техподдержки (GLPI)
GLPI_REST_URL = os.getenv("GLPI_REST_URL", "http://192.168.222.96/apirest.php")
#GLPI_USER_TOKEN = os.getenv("GLPI_USER_TOKEN", "agGB1CpuY21nN5FqY7X1FPbVBydmOhHM2BvBR4qS")
#GLPI_API_TOKEN = os.getenv("GLPI_API_TOKEN", "EkgIi2puJ3pysg6J1Kzs02DGP5PPWkIaWYYrGnaT")
GLPI_USER_TOKEN = "agGB1CpuY21nN5FqY7X1FPbVBydmOhHM2BvBR4qS"
GLPI_APP_TOKEN = "EkgIi2puJ3pysg6J1Kzs02DGP5PPWkIaWYYrGnaT"

# Настройки векторной БД Qdrant (ВМ 2)
QDRANT_URL = os.getenv("QDRANT_URL", "http://192.168.222.66:6333")
COLLECTION_NAME = "factory_regulations"

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ КОМПОНЕНТОВ ИИ (ЛОКАЛЬНО)
# ==========================================
# Локальная языковая модель Saiga3
llm = ChatOllama(
    base_url=OLLAMA_BASE_URL,
    model="saiga3",
    temperature=0.2
)

# Локальные эмбеддинги, строго соответствующие вашей модели в базе Qdrant
embeddings = OllamaEmbeddings(
    base_url=OLLAMA_BASE_URL,
    model="bge-m3:latest" 
)

# Корректная инициализация векторного хранилища через langchain_qdrant
#client = QdrantClient(url=QDRANT_URL)
#vectorstore = Qdrant(
#    client=client, 
#    collection_name=COLLECTION_NAME, 
#    embeddings=embeddings
#)
client = QdrantClient(url=QDRANT_URL)

vectorstore = QdrantVectorStore.from_existing_collection(
    embedding=embeddings,
    collection_name=COLLECTION_NAME,
    url=QDRANT_URL
)

retriever = vectorstore.as_retriever(search_kwargs={"k": 3})
# Метод as_retriever() теперь будет правильно вызывать внутренний поиск LangChain
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ СЕРВИСНЫЕ ФУНКЦИИ
# ==========================================

def mask_personal_data(text: str) -> str:
    """
    Модуль деидентификации (План Б без тяжелого SpaCy).
    Маскирует ФИО, номера телефонов, IP-адреса и АРМ для соблюдения требований ИБ АО 'Омский каучук'.
    """
    if not text:
        return ""
    # Маскирование IP-адресов
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP_REDACTED]', text)
    # Маскирование номеров телефонов (включая внутренние заводские)
    text = re.sub(r'(\+7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}([\s\-]?\d{2}){2}|\b\d{4}\b', '[PHONE_REDACTED]', text)
    # Маскирование номеров рабочих станций (АРМ №123)
    text = re.sub(r'(АРМ|ARM)[\s№_-]*\d+', '[ARM_REDACTED]', text)
    return text


#def post_solution_to_glpi(ticket_id: int, solution_text: str):
    """
     Исходящее плечо интеграции: передает сгенерированный ИИ ответ 
     обратно в GLPI, меняя статус тикета на 'Решено' (status=2)
    """
# 1. Открываем API-сессию в GLPI
#    init_url = f"{GLPI_REST_URL}/initSession"
#    headers = {"Authorization": f"user_token {GLPI_USER_TOKEN}"}

# 1. Открываем API-сессию в GLPI
#    init_url = f"{GLPI_REST_URL}/initSession"
#
#    # ПРАВИЛЬНЫЕ ЗАГОЛОВКИ ДЛЯ GLPI API:
#    headers = {
#        "User-Token": GLPI_USER_TOKEN,
#        "Content-Type": "application/json"
#    }
#
#    # ЕСЛИ в GLPI включен App-Token, раскомментируйте строку ниже и вставьте его:
#    headers["App-Token"] = "EkgIi2puJ3pysg6J1Kzs02DGP5PPWkIaWYYrGnaT"
#    try:
#        session_res = requests.get(init_url, headers=headers, timeout=5)
#        session_res.raise_for_status()
#        session_token = session_res.json()["session_token"]
#    except Exception as e:
#        print(f"[GLPI Integration Error] Ошибка авторизации: {e}")
#        return
#
#    # 2. Формируем заголовки для работы с тикетом
#    auth_headers = {
#        "Session-Token": session_token,
#        "Content-Type": "application/json"
#    }
#    solution_url = f"{GLPI_REST_URL}/Ticket/{ticket_id}/ITILSolution"
#   
#    # Оформляем красивый HTML-ответ для интерфейса GLPI
#    payload = {
#        "input": {
#            "items_id": ticket_id,
#            "itemtype": "Ticket",
#            "content": f"<b>Автоматическое решение ИИ-ассистента:</b><br><br>{solution_text}<br><br><small><i>Ответ сгенерирован автоматически локальной моделью Saiga Llama-3.</i></small>",
#            "status": 2  # Статус 'Решено' в GLPI
#        }
#    }
    
#    try:
#        # Отправляем POST-запрос с решением
#        response = requests.post(solution_url, headers=auth_headers, json=payload, timeout=5)
#        if response.status_code == 201:
#            print(f"[GLPI Success] Решение успешно добавлено в тикет #{ticket_id}")
#        else:
#            print(f"[GLPI Error] Не удалось отправить решение: {response.text}")
#    except Exception as e:
#        print(f"[GLPI Integration Error] Ошибка отправки решения: {e}")
#    finally:
#        # 3. В любом случае закрываем сессию, чтобы не плодить зомби-процессы
#        requests.get(f"{GLPI_REST_URL}/killSession", headers={"Session-Token": session_token}, timeout=5)

def post_solution_to_glpi(ticket_id: int, solution_text: str):
    """
    Исходящее плечо интеграции: передает сгенерированный ИИ ответ 
    обратно в GLPI через сущность ITILSolution.
    Автоматически переводит статус тикета в 'Решено' (status=5).
    """
    # 1. Открываем API-сессию в GLPI
    init_url = f"{GLPI_REST_URL}/initSession"
    
    # Заголовки для авторизации (App-Token обязателен, если включен в GLPI)
    init_headers = {
        "User-Token": GLPI_USER_TOKEN,
        "App-Token": GLPI_APP_TOKEN,
        "Content-Type": "application/json"
    }
    
    session_token = None
    try:
        # Отправляем GET-запрос для инициализации сессии
        session_res = requests.get(init_url, headers=init_headers, timeout=5)
        session_res.raise_for_status()
        session_token = session_res.json()["session_token"]
    except Exception as e:
        print(f"[GLPI Integration Error] Ошибка авторизации: {e}")
        return

    # 2. Формируем заголовки и эндпоинт для работы с решением
    auth_headers = {
        "Session-Token": session_token,
        "App-Token": GLPI_APP_TOKEN,
        "Content-Type": "application/json"
    }
    
    # ИСПРАВЛЕНО: Эндпоинт для создания решения всегда плоский
    solution_url = f"{GLPI_REST_URL}/ITILSolution"
    
    # Формируем HTML-текст ответа
    html_content = (
        f"<b>Автоматическое решение ИИ-ассистента:</b><br><br>"
        f"{solution_text}<br><br>"
        f"<small><i>Ответ сгенерирован автоматически локальной моделью Saiga Llama-3.</i></small>"
    )
    
    payload = {
        "input": {
            "itemtype": "Ticket",
            "items_id": ticket_id,
            "content": html_content,
            # ИСПРАВЛЕНО: статус решения 2 означает 'Согласовано/Утверждено' (в зависимости от настроек),
            # при добавлении ITILSolution сам тикет автоматически получит статус 5 (Решено).
            "status": 2  
        }
    }
    
    try:
        # ИСПРАВЛЕНО: GLPI возвращает 201 Created при успешном создании объекта
        response = requests.post(solution_url, headers=auth_headers, json=payload, timeout=5)
        if response.status_code == 201:
            print(f"[GLPI Success] Решение успешно добавлено в тикет #{ticket_id}. Статус изменен на 'Решено'.")
        else:
            print(f"[GLPI Error] Не удалось отправить решение. Код: {response.status_code}. Ответ: {response.text}")
    except Exception as e:
        print(f"[GLPI Integration Error] Ошибка отправки решения: {e}")
        
    finally:
        # 3. Закрываем сессию (Обязательно передаем App-Token)
        if session_token:
            try:
                requests.get(
                    f"{GLPI_REST_URL}/killSession", 
                    headers={"Session-Token": session_token, "App-Token": GLPI_APP_TOKEN}, 
                    timeout=5
                )
            except Exception:
                pass  # Игнорируем ошибки закрытия, чтобы не прерывать основной поток



# ==========================================
# 4. СБОРКА ИНТЕЛЛЕКТУАЛЬНОЙ ЦЕПОЧКИ LANGCHAIN
# ==========================================
# Системный промт для Saiga, адаптированный под регламенты химического предприятия
prompt_template = ChatPromptTemplate.from_messages([
    ("system", (
        "Ты — ведущий ИИ-специалист службы ИТ-поддержки химического предприятия.\n"
        "Твоя задача — помочь пользователю решить его проблему, строго опираясь на предоставленный контекст (инструкции).\n"
        "Если в контексте нет ответа на вопрос, ответь вежливо: 'К сожалению, в базе знаний нет решения для данной проблемы. Заявка перенаправлена инженеру L2.'\n\n"
        "Контекст из базы знаний:\n{context}"
    )),
    ("user", "Заявка от сотрудника: {query}")
])

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

# Классический RAG-конвейер
rag_chain = (
    {"context": retriever | format_docs, "query": RunnablePassthrough()}
    | prompt_template
    | llm
    | StrOutputParser()
)

# ==========================================
# 5. API ЭНДПОИНТ (ТОЧКА ВХОДА ДЛЯ ВЕБХУКА)
# ==========================================

@app.post("/api/v1/glpi-webhook")
async def handle_glpi_webhook(request: Request):
    """
    Основной эндпоинт, который GLPI вызывает на лету при создании нового тикета.
    Реализует синхронный Event-Driven цикл обработки.
    """
    try:
        # Читаем сначала как чистый сырой текст, чтобы не падать сразу
        raw_body = await request.body()
        raw_text = raw_body.decode("utf-8")

        # Выводим в лог до парсинга, чтобы поймать виновника ошибки
        print(f"\n[DEBUG RAW BODY]: {raw_text}\n")

        # Пытаемся распарсить стандартным методом логов
        import json
        payload = json.loads(raw_text)
        # Принимаем сырой JSON от плагина Webhooks системы GLPI
        payload = await request.json()
        
        # Извлекаем ID тикета и текст обращения заводчанина
        ticket_id = payload.get("event_data", {}).get("id")
        raw_user_query = payload.get("event_data", {}).get("content")
        
        if not ticket_id or not raw_user_query:
            raise HTTPException(status_code=400, detail="Неверная структура JSON-пакета вебхука GLPI")
            
        print(f"[ITSM Gateway] Поступил тикет #{ticket_id}. Запуск интеллектуальной обработки...")
        
        # Шаг 1. Обеспечение ИБ (Маскирование ПДн)
        safe_query = mask_personal_data(raw_user_query)
        
        # Шаг 2. Генерация ответа через RAG и Ollama
        ai_response = rag_chain.invoke(safe_query)
        
        # Шаг 3. Синхронный возврат ответа и закрытие задачи в ITSM-системе
        post_solution_to_glpi(ticket_id, ai_response)
        
        return {"status": "success", "processed_ticket_id": ticket_id}
        
    except Exception as e:
        print(f"[Webhook Critical Error] Ошибка в конвейере обработки: {str(e)}")
        return {"status": "error", "detail": str(e)}
