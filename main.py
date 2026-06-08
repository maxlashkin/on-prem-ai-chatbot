
import os
import re
import requests
import json
import markdown  # Добавлен импорт для обработки разметки
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any

# Актуальные импорты LangChain
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

app = FastAPI(
    title="ITSM AI Integration Gateway",
    description="Компонент MVP для синхронной интеграции GLPI, Qdrant и Ollama (v2.0)"
)

# ==========================================
# 1. КОНФИГУРАЦИЯ (ВМ И ТОКЕНЫ)
# ==========================================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.222.66:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://192.168.222.66:6333")
GLPI_REST_URL = os.getenv("GLPI_REST_URL", "http://192.168.222.96/apirest.php")

GLPI_USER_TOKEN = "agGB1CpuY21nN5FqY7X1FPbVBydmOhHM2BvBR4qS"
GLPI_APP_TOKEN = "EkgIi2puJ3pysg6J1Kzs02DGP5PPWkIaWYYrGnaT"
COLLECTION_NAME = "factory_regulations"

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ ИИ-КОМПОНЕНТОВ
# ==========================================
llm = ChatOllama(
    base_url=OLLAMA_BASE_URL,
    model="saiga3",
    temperature=0.2
)

embeddings = OllamaEmbeddings(
    base_url=OLLAMA_BASE_URL,
    model="bge-m3:latest"
)

client = QdrantClient(url=QDRANT_URL)
vectorstore = QdrantVectorStore.from_existing_collection(
    embedding=embeddings,
    collection_name=COLLECTION_NAME,
    url=QDRANT_URL
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

# ==========================================
# 3. СЕРВИСНЫЕ ФУНКЦИИ
# ==========================================

def mask_personal_data(text: str) -> str:
    """Маскирование ПДн (IP, Телефоны, АРМ)."""
    if not text: return ""
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP_REDACTED]', text)
    text = re.sub(r'(\+7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}([\s\-]?\d{2}){2}|\b\d{4}\b', '[PHONE_REDACTED]', text)
    text = re.sub(r'(АРМ|ARM)[\s№_-]*\d+', '[ARM_REDACTED]', text)
    return text

#def post_solution_to_glpi(ticket_id: int, solution_text: str):
#    """Отправка решения в GLPI с исправленной авторизацией и рендерингом Markdown."""
#    session_token = None
#    
#    # ПРЕОБРАЗОВАНИЕ MARKDOWN -> HTML
#    # nl2br сохраняет переносы строк, sane_lists делает списки красивыми
#    solution_html = markdown.markdown(solution_text, extensions=['nl2br', 'sane_lists'])
#    
#    # 1. Инициализация сессии
#    init_headers = {
#        "Authorization": f"user_token {GLPI_USER_TOKEN}",
#        "App-Token": GLPI_APP_TOKEN,
#        "Content-Type": "application/json"
#    }
#    
#    try:
#        res = requests.get(f"{GLPI_REST_URL}/initSession", headers=init_headers, timeout=10)
#        if res.status_code != 200:
#            print(f"[GLPI Auth Error] Код: {res.status_code}, Ответ: {res.text}")
#            return
#        session_token = res.json().get("session_token")
#    except Exception as e:
#        print(f"[GLPI Connection Error] Не удалось связаться с сервером: {e}")
#        return
#
#    # 2. Добавление решения
#    auth_headers = {
#        "Session-Token": session_token,
#        "App-Token": GLPI_APP_TOKEN,
#        "Content-Type": "application/json"
#    }
#    
#    payload = {
#        "input": {
#            "itemtype": "Ticket",
#            "items_id": ticket_id,
#            "content": (
#                f"<b>Автоматическое решение ИИ-ассистента:</b><br><br>"
#                f"{solution_html}<br><br>"
#                f"<small><i>Сгенерировано локальной LLM Saiga3 (RAG).</i></small>"
#            ),
#            "status": 2 # Принято/Решено
#        }
#    }

#    try:
#        sol_res = requests.post(f"{GLPI_REST_URL}/ITILSolution", headers=auth_headers, json=payload, timeout=10)
#        if sol_res.status_code == 201:
#            print(f"[GLPI Success] Решение успешно добавлено в HTML для тикета #{ticket_id}")
#        else:
#            print(f"[GLPI Error] Ошибка добавления решения: {sol_res.text}")
#    finally:
#        if session_token:
#            requests.get(f"{GLPI_REST_URL}/killSession", headers=auth_headers, timeout=5)
def post_solution_to_glpi(ticket_id: int, solution_text: str):
    """Добавляет ответ ИИ как комментарий (Follow-up), не закрывая заявку."""
    session_token = None
    
    # Преобразование Markdown в HTML (оставляем, чтобы было красиво)
    solution_html = markdown.markdown(solution_text, extensions=['nl2br', 'sane_lists'])
    
    init_headers = {
        "Authorization": f"user_token {GLPI_USER_TOKEN}",
        "App-Token": GLPI_APP_TOKEN,
        "Content-Type": "application/json"
    }
    
    try:
        # 1. Инициализация сессии
        res = requests.get(f"{GLPI_REST_URL}/initSession", headers=init_headers, timeout=10)
        if res.status_code != 200:
            print(f"[GLPI Auth Error] Код: {res.status_code}, Ответ: {res.text}")
            return
        session_token = res.json().get("session_token")

        # 2. Добавление комментария (ITILFollowup)
        auth_headers = {
            "Session-Token": session_token,
            "App-Token": GLPI_APP_TOKEN,
            "Content-Type": "application/json"
        }
        
        # ВАЖНО: используем ITILFollowup вместо ITILSolution
        followup_url = f"{GLPI_REST_URL}/ITILFollowup"
        
        payload = {
            "input": {
                "itemtype": "Ticket",
                "items_id": ticket_id,
                "content": (
                    f"<b>🤖 Предложение от ИИ-ассистента:</b><br><br>"
                    f"{solution_html}<br><br>"
                    f"<small><i>Ответ добавлен автоматически. Заявка остается в работе.</i></small>"
                ),
                "is_private": 0  # 0 = публичный комментарий (виден автору), 1 = скрытый
            }
        }

        # Отправляем POST запрос
        sol_res = requests.post(followup_url, headers=auth_headers, json=payload, timeout=10)
        
        if sol_res.status_code == 201:
            print(f"[GLPI Success] Комментарий добавлен в тикет #{ticket_id}. Статус не изменен.")
        else:
            print(f"[GLPI Error] Не удалось добавить комментарий: {sol_res.text}")

    except Exception as e:
        print(f"[GLPI Connection Error] {e}")
    finally:
        if session_token:
            requests.get(f"{GLPI_REST_URL}/killSession", headers=auth_headers, timeout=5)

# ==========================================
# 4. ЦЕПОЧКА RAG (ASYNC READY)
# ==========================================
prompt_template = ChatPromptTemplate.from_messages([
    ("system", (
        "Ты — ведущий ИИ-специалист службы ИТ-поддержки завода Омский каучук.\n"
        "Помоги пользователю, используя только предоставленный контекст. Используй списки и заголовки Markdown для оформления.\n"
        "Если ответа нет в контексте, ответь: 'Решение не найдено в локальной базе знаний. Заявка передана на уровень L2.'\n\n"
        "Инструкции из базы знаний:\n{context}"
    )),
    ("user", "Заявка: {query}")
])

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

rag_chain = (
    {"context": retriever | format_docs, "query": RunnablePassthrough()}
    | prompt_template
    | llm
    | StrOutputParser()
)

# ==========================================
# 5. ЭНДПОИНТ ВЕБХУКА (ASYNC)
# ==========================================
@app.post("/api/v1/glpi-webhook")
async def handle_glpi_webhook(request: Request):
    # 1. Читаем сырое тело и заголовки для диагностики
    raw_body = await request.body()
    headers = dict(request.headers)
    print(f"[DEBUG] Headers: {headers}")
    print(f"[DEBUG] Raw body (bytes): {raw_body}")
    print(f"[DEBUG] Raw body (decoded): {raw_body.decode('utf-8', errors='replace')}")

    # 2. Пытаемся распарсить JSON, если тело не пустое
    payload = None
    if raw_body:
        try:
            payload = await request.json()
            print(f"[DEBUG] Parsed JSON: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        except Exception as json_err:
            print(f"[WARN] Failed to parse JSON: {json_err}")
            # Пытаемся интерпретировать как form-data или plain text
            body_text = raw_body.decode('utf-8', errors='replace')
            # Можно попробовать извлечь id из query string, если тело пустое
            # Но пока просто вернём ошибку с пояснением
            return {"status": "error", "message": f"Invalid JSON body: {body_text[:100]}"}
    else:
        print("[WARN] Request body is empty!")
        # Если тело пустое, возможно, GLPI передаёт данные в query параметрах
        query_params = dict(request.query_params)
        if query_params:
            print(f"[DEBUG] Query params: {query_params}")
            # Можно попробовать достать ticket_id из query, но обычно GLPI так не делает
        # Всё равно возвращаем ошибку, но с понятным сообщением
        return {"status": "error", "message": "Empty request body, cannot process webhook"}

    # 3. Если payload получен, извлекаем данные
    if not payload:
        return {"status": "error", "message": "No payload"}

    # Здесь ваша логика: проверка наличия event_data, id, content и т.д.
    event_data = payload.get("event_data", {})
    ticket_id = event_data.get("id")
    user_query = event_data.get("content")

    if not ticket_id or not user_query:
        # Логируем весь payload для анализа
        print(f"[WARN] Missing ticket_id or content in payload: {payload}")
        return {"status": "ignored", "reason": "Missing ticket_id or content"}

    print(f"[ITSM Gateway] Тикет #{ticket_id}: Начало обработки...")

    safe_query = mask_personal_data(user_query)

    # Вызов ИИ (Async)
    ai_response = await rag_chain.ainvoke(safe_query)
    print(f"[ITSM Gateway] Тикет #{ticket_id}: Ответ сформирован.")

    # Отправка ответа в GLPI
    post_solution_to_glpi(ticket_id, ai_response)

    return {"status": "success", "ticket_id": ticket_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
