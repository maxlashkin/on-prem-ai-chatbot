import os
import re
import requests
import json
import markdown  # Добавлен импорт для обработки разметки
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any
from fastapi.middleware.cors import CORSMiddleware


# Актуальные импорты LangChain
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

app = FastAPI(
    title="ITSM AI Integration Gateway",
    description="Компонент MVP для синхронной интеграции GLPI, Qdrant и Ollama (v3.0 - Enterprise)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Для диплома оставляем "*", чтобы на защите CORS ничего не заблокировал
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
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
# 3. СЕРВИСНЫЕ ФУНКЦИИ И ОПТИМИЗАЦИЯ СЕТИ
# ==========================================

def mask_personal_data(text: str) -> str:
    """Маскирование ПДн (IP, Телефоны, АРМ)."""
    if not text: return ""
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP_REDACTED]', text)
    text = re.sub(r'(\+7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}([\s\-]?\d{2}){2}|\b\d{4}\b', '[PHONE_REDACTED]', text)
    text = re.sub(r'(АРМ|ARM)[\s№_-]*\d+', '[ARM_REDACTED]', text)
    return text

def post_solution_to_glpi(ticket_id: int, solution_text: str):
    """Добавляет ответ ИИ как публичный комментарий (Follow-up), не закрывая заявку."""
    session_token = None
    solution_html = markdown.markdown(solution_text, extensions=['nl2br', 'sane_lists'])
    
    init_headers = {
        "Authorization": f"user_token {GLPI_USER_TOKEN}",
        "App-Token": GLPI_APP_TOKEN,
        "Content-Type": "application/json"
    }
    
    try:
        res = requests.get(f"{GLPI_REST_URL}/initSession", headers=init_headers, timeout=10)
        if res.status_code != 200:
            print(f"[GLPI Auth Error] Код: {res.status_code}, Ответ: {res.text}")
            return
        session_token = res.json().get("session_token")

        auth_headers = {
            "Session-Token": session_token,
            "App-Token": GLPI_APP_TOKEN,
            "Content-Type": "application/json"
        }
        
        payload = {
            "input": {
                "itemtype": "Ticket",
                "items_id": ticket_id,
                "content": (
                    f"<b>🤖 Предложение от ИИ-ассистента (RAG):</b><br><br>"
                    f"{solution_html}<br><br>"
                    f"<small><i>Ответ добавлен автоматически на основе базы знаний завода.</i></small>"
                ),
                "is_private": 0  
            }
        }

        sol_res = requests.post(f"{GLPI_REST_URL}/ITILFollowup", headers=auth_headers, json=payload, timeout=10)
        if sol_res.status_code == 201:
            print(f"[GLPI Success] Комментарий успешно добавлен в тикет #{ticket_id}.")
        else:
            print(f"[GLPI Error] Не удалось добавить комментарий: {sol_res.text}")

    except Exception as e:
        print(f"[GLPI Connection Error] {e}")
    finally:
        if session_token:
            requests.get(f"{GLPI_REST_URL}/killSession", headers=auth_headers, timeout=5)

def create_ticket_via_api(title: str, content: str, glpi_user_id: int = None) -> int:
    """Создает новую заявку в GLPI, привязывая её к конкретному пользователю."""
    session_token = None
    init_headers = {
        "Authorization": f"user_token {GLPI_USER_TOKEN}",
        "App-Token": GLPI_APP_TOKEN,
        "Content-Type": "application/json"
    }
    
    try:
        res = requests.get(f"{GLPI_REST_URL}/initSession", headers=init_headers, timeout=10)
        if res.status_code != 200:
            return 0
        session_token = res.json().get("session_token")

        auth_headers = {
            "Session-Token": session_token,
            "App-Token": GLPI_APP_TOKEN,
            "Content-Type": "application/json"
        }
        
        clean_title = title.strip().replace("\n", " ")
        if len(clean_title) > 60:
            clean_title = clean_title[:57] + "..."

        # Базовый payload создания заявки
        ticket_input = {
            "name": clean_title,
            "content": content,
            "urgency": 3,
            "impact": 3,
            "status": 1
        }

        # Если фронтенд передал ID реального пользователя, подставляем его как автора!
        if glpi_user_id:
            # В GLPI связь тикета с автором часто идет через массив или явные поля:
            ticket_input["_users_id_requester"] = glpi_user_id  # Для стандартных форм
            ticket_input["users_id_recipient"] = glpi_user_id   # Получатель

        payload = {"input": ticket_input}

        ticket_res = requests.post(f"{GLPI_REST_URL}/Ticket", headers=auth_headers, json=payload, timeout=10)
        if ticket_res.status_code == 201:
            return ticket_res.json().get("id")
        return 0

    except Exception as e:
        print(f"[GLPI API Exception] {e}")
        return 0
    finally:
        if session_token:
            requests.get(f"{GLPI_REST_URL}/killSession", headers=auth_headers, timeout=5)

# ==========================================
# 4. СТАНДАРТНАЯ ЦЕПОЧКА RAG ДЛЯ ВЕБХУКОВ
# ==========================================
prompt_template = ChatPromptTemplate.from_messages([
    ("system", (
        "Ты — ведущий ИИ-специалист службы ИТ-поддержки завода Омский каучук.\n"
        "Помоги пользователю, используя только предоставленный контекст. Используй списки и заголовки Markdown для оформления.\n"
        "Если точного ответа нет в контексте, ответь ровно одной фразой: 'ДАННЫЕ_НЕ_НАЙДЕНЫ'\n\n"
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
# 5. ЭНДПОИНТ ВЕБХУКА (СТРАТЕГИЯ SILENT SKIP)
# ==========================================
@app.post("/api/v1/glpi-webhook")
async def handle_glpi_webhook(request: Request):
    raw_body = await request.body()
    if not raw_body:
        return {"status": "error", "message": "Empty request body"}

    try:
        payload = await request.json()
    except Exception as json_err:
        return {"status": "error", "message": "Invalid JSON body"}

    event_data = payload.get("event_data", {})
    ticket_id = event_data.get("id")
    user_query = event_data.get("content")

    if not ticket_id or not user_query:
        return {"status": "ignored", "reason": "Missing ticket_id or content"}

    print(f"[ITSM Gateway] Тикет #{ticket_id}: Проверка во внутренних регламентах...")
    safe_query = mask_personal_data(user_query)

    # Запускаем генерацию ответа
    ai_response = await rag_chain.ainvoke(safe_query)

    # СТРАТЕГИЯ МИНИМИЗАЦИИ ЛОЖНЫХ СРАБАТЫВАНИЙ (Silent Skip)
    if "ДАННЫЕ_НЕ_НАЙДЕНЫ" in ai_response or len(ai_response.strip()) < 25:
        print(f"[ITSM Gateway] Тикет #{ticket_id}: Инструкция в RAG не найдена. Робот пропускает тикет для ручного разбора инженерами.")
        return {"status": "skipped", "reason": "No relevant instructions found in Qdrant"}

    print(f"[ITSM Gateway] Тикет #{ticket_id}: Решение успешно найдено. Публикация в GLPI...")
    post_solution_to_glpi(ticket_id, ai_response)

    return {"status": "success", "ticket_id": ticket_id}

# ==========================================
# 6. ЭНДПОИНТ ОПЕРАТИВНОЙ ПОДСКАЗКИ (ИНТРАКТИВНЫЙ UI)
# ==========================================
@app.post("/api/v1/chat")
async def chat_assistant(request: Request):
    """
    Эндпоинт для виджета оперативной подсказки диспетчера/самообслуживания.
    Возвращает контент или маркер действия для генерации кнопок во фронтенде.
    """
    try:
        data = await request.json()
        user_text = data.get("text", "").strip()
        
        if not user_text or len(user_text) < 10:
            return {"response": ""}

        # 1. Прямой поиск в Qdrant (без дублирования вызовов цепочки)
        docs = retriever.invoke(user_text)
        
        # Если Qdrant вернул пустой список документов, сразу прерываемся и отдаем управляющий флаг
        if not docs or len(docs) == 0:
            return {"response": "ДАННЫЕ_НЕ_НАЙДЕНЫ"}
            
        context = "\n".join([doc.page_content for doc in docs])
        
        # Дополнительная валидация контекста (на случай, если прилетел нерелевантный мусор)
        if not context.strip():
            return {"response": "ДАННЫЕ_НЕ_НАЙДЕНЫ"}

        # 2. Генерируем финальный понятный ответ с помощью Saiga3
        prompt = (
            f"Ты — ИИ-помощник ИТ-поддержки. Используя только указанные инструкции, ответь на вопрос.\n"
            f"Если в инструкциях нет ответа, напиши только одно слово: ДАННЫЕ_НЕ_НАЙДЕНЫ\n\n"
            f"Инструкции:\n{context}\n\n"
            f"Вопрос пользователя: {user_text}"
        )
        
        ai_answer = llm.invoke(prompt).content
        
        if "ДАННЫЕ_НЕ_НАЙДЕНЫ" in ai_answer:
            return {"response": "ДАННЫЕ_НЕ_НАЙДЕНЫ"}

        return {"response": ai_answer}
        
    except Exception as e:
        print(f"[API ERROR] Ошибка в блоке чата: {str(e)}")
        return {"response": f"Ошибка связи с ИИ-модулем: {str(e)}"}

# Новый эндпоинт для обработки клика «Оформить заявку»
@app.post("/api/v1/create-ticket")
async def api_create_ticket(request: Request):
    try:
        data = await request.json()
        raw_text = data.get("text", "").strip()
        # Принимаем ID пользователя из запроса
        glpi_user_id = data.get("user_id") 
        
        if not raw_text:
            raise HTTPException(status_code=400, detail="Текст заявки пуст")
            
        safe_text = mask_personal_data(raw_text)
        
        # Передаем ID пользователя в функцию создания
        ticket_id = create_ticket_via_api(title=raw_text, content=safe_text, glpi_user_id=glpi_user_id)
        
        if ticket_id > 0:
            return {"status": "success", "ticket_id": ticket_id}
        else:
            return {"status": "error", "message": "Не удалось создать тикет через API"}
            
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
