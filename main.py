import os
import re
import requests
import json
import markdown
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Dict, Any, List
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
    description="Компонент MVP с двухэтапной валидацией ИТ-тематики и выводом сниппетов (v4.2-Secure)"
)

# Разрешаем CORS для бесшовной интеграции с фронтендом GLPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Для диплома оставляем "*", чтобы на защите не заблокировались запросы
    allow_credentials=True,
    allow_methods=["*"], 
    allow_headers=["*"], 
)

# ==========================================
# 1. КОНФИГУРАЦИЯ (ВМ, АДРЕСА И ТОКЕНЫ)
# ==========================================
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.222.66:11434")
QDRANT_URL = os.getenv("QDRANT_URL", "http://192.168.222.66:6333")
GLPI_REST_URL = os.getenv("GLPI_REST_URL", "http://192.168.222.96/apirest.php")

GLPI_USER_TOKEN = "agGB1CpuY21nN5FqY7X1FPbVBydmOhHM2BvBR4qS"
GLPI_APP_TOKEN = "EkgIi2puJ3pysg6J1Kzs02DGP5PPWkIaWYYrGnaT"
COLLECTION_NAME = "factory_regulations"

# ==========================================
# 2. ИНИЦИАЛИЗАЦИЯ ИИ КОМПОНЕНТОВ
# ==========================================
llm = ChatOllama(base_url=OLLAMA_BASE_URL, model="saiga3", temperature=0.1)  # Низкая температура для стабильности классификации
embeddings = OllamaEmbeddings(base_url=OLLAMA_BASE_URL, model="bge-m3:latest")

client = QdrantClient(url=QDRANT_URL)
vectorstore = QdrantVectorStore.from_existing_collection(
    embedding=embeddings, collection_name=COLLECTION_NAME, url=QDRANT_URL
)
retriever = vectorstore.as_retriever(search_kwargs={"k": 2})

# ==========================================
# 3. ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ И МАСКИРОВАНИЕ
# ==========================================
def mask_personal_data(text: str) -> str:
    if not text: return ""
    text = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP_REDACTED]', text)
    text = re.sub(r'(\+7|8)?[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}([\s\-]?\d{2}){2}|\b\d{4}\b', '[PHONE_REDACTED]', text)
    text = re.sub(r'(АРМ|ARM)[\s№_-]*\d+', '[ARM_REDACTED]', text)
    return text

def extract_context_and_sources(query: str):
    """Извлекает текст документов и их имена файлов со сниппетами из Qdrant."""
    try:
        docs = retriever.invoke(query)
    except Exception as e:
        print(f"[Qdrant Error] {e}")
        return "", []
        
    context_text = "\n\n".join([doc.page_content for doc in docs])
    
    sources_detailed = []
    seen_chunks = set()
    
    for doc in docs:
        meta = doc.metadata
        name = meta.get("file_name") or meta.get("source") or meta.get("title") or "Инструкция.pdf"
        name = os.path.basename(name)
        
        chunk_content = doc.page_content.strip()
        if chunk_content and chunk_content not in seen_chunks:
            seen_chunks.add(chunk_content)
            sources_detailed.append({
                "file_name": name,
                "snippet": chunk_content
            })
                
    return context_text, sources_detailed

def post_solution_to_glpi(ticket_id: int, solution_text: str, sources: List[dict]):
    session_token = None
    solution_html = markdown.markdown(solution_text, extensions=['nl2br', 'sane_lists'])

    sources_html = ""
    if sources:
        file_names = set([s.get("file_name", "Инструкция") for s in sources])
        sources_html = "<br><br><b>Использованные нормативные документы базы знаний:</b><ul>" + "".join([f"<li>📄 {name}</li>" for name in file_names]) + "</ul>"

    init_headers = {"Authorization": f"user_token {GLPI_USER_TOKEN}", "App-Token": GLPI_APP_TOKEN, "Content-Type": "application/json"}
    try:
        res = requests.get(f"{GLPI_REST_URL}/initSession", headers=init_headers, timeout=10)
        if res.status_code != 200: return
        session_token = res.json().get("session_token")

        auth_headers = {"Session-Token": session_token, "App-Token": GLPI_APP_TOKEN, "Content-Type": "application/json"}
        
        payload = {
            "input": {
                "itemtype": "Ticket",
                "items_id": ticket_id,
                "content": f"<b>🤖 Решение от ИИ:</b><br><br>{solution_html}{sources_html}<hr style='border: 0; border-top: 1px solid #e2e8f0; margin: 10px 0 5px 0;'><small style='color: #94a3b8; font-style: italic;'>ИИ может ошибаться. Рекомендуем проверять ответы.</small>",
                "is_private": 0
            }
        }
        
        requests.post(f"{GLPI_REST_URL}/ITILFollowup", headers=auth_headers, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки комментария в GLPI: {e}")
    finally:
        if session_token:
            requests.get(f"{GLPI_REST_URL}/killSession", headers=auth_headers, timeout=5)

def create_ticket_via_api(title: str, content: str, glpi_user_id: int = None) -> int:
    session_token = None
    init_headers = {"Authorization": f"user_token {GLPI_USER_TOKEN}", "App-Token": GLPI_APP_TOKEN, "Content-Type": "application/json"}
    try:
        res = requests.get(f"{GLPI_REST_URL}/initSession", headers=init_headers, timeout=10)
        if res.status_code != 200: return 0
        session_token = res.json().get("session_token")
        auth_headers = {"Session-Token": session_token, "App-Token": GLPI_APP_TOKEN, "Content-Type": "application/json"}
        
        clean_title = title.strip().replace("\n", " ")
        if len(clean_title) > 60: clean_title = clean_title[:57] + "..."

        ticket_input = {"name": clean_title, "content": content, "urgency": 3, "impact": 3, "status": 1}
        if glpi_user_id:
            ticket_input["_users_id_requester"] = glpi_user_id  
            ticket_input["users_id_recipient"] = glpi_user_id   

        payload = {"input": ticket_input}
        ticket_res = requests.post(f"{GLPI_REST_URL}/Ticket", headers=auth_headers, json=payload, timeout=10)
        if ticket_res.status_code == 201: return ticket_res.json().get("id")
        return 0
    except Exception as e:
        print(f"Ошибка создания тикета через API: {e}")
        return 0
    finally:
        if session_token: requests.get(f"{GLPI_REST_URL}/killSession", headers=auth_headers, timeout=5)

# ==========================================
# 4. ВЫДЕЛЕННЫЕ ЦЕПОЧЕКИ ПРОМПТОВ (GUARDRAILS)
# ==========================================

# СЛОЙ 1: Абсолютный классификатор темы (Входной фильтр)
prompt_classifier = ChatPromptTemplate.from_messages([
    ("system", (
        "Ты — автоматический шлюз-классификатор обращений в ИТ-поддержку завода Омский каучук.\n"
        "Твоя единственная цель — определить, относится ли текст к сфере информационных технологий, вычислительной техники или оргтехники.\n\n"
        "ЦЕЛЕВЫЕ ТЕМЫ (относятся к ИТ): Компьютеры, мониторы, мыши, принтеры, картриджи, Kyocera, Windows, Active Directory, пароли, сети, Wi-Fi, 1С, СЭД, почта, СУБД, телефония, ремонт техники.\n"
        "НЕЦЕЛЕВЫЕ ТЕМЫ (не относятся к ИТ): Приветствия, 'как дела', погода, кулинария, ремонт мебели, заказ канцтоваров, философия, шутки, абстрактные вопросы.\n\n"
        "ПРАВИЛО ОТВЕТА:\n"
        "- Если запрос СВЯЗАН с ИТ или оргтехникой, верни РОВНО ОДИН СИМВОЛ: 1\n"
        "- Если запрос НЕ связан с ИТ (флуд, офтоп, приветствие), верни РОВНО ОДИН СИМВОЛ: 0\n"
        "- Не пиши никаких вводных слов, знаков препинания или объяснений. Только цифру 1 или 0."
    )),
    ("user", "Запрос пользователя: {query}")
])

# СЛОЙ 2: Экспресс-генератор коротких ответов (для виджета)
#prompt_short = ChatPromptTemplate.from_messages([
#    ("system", (
#        "Ты — ИИ-инженер ИТ-поддержки завода Омский каучук.\n"
#        "Твоя задача — выдать КРАТКОЕ, строго тезисное ИТ-решение для всплывающей подсказки оператора (3-4 лаконичных пункта).\n"
#        "Пиши исключительно технические шаги. Никакой воды, приветствий или вежливых заключений.\n\n"
#        "Контекст из регламентов завода:\n{context}"
#    )),
#    ("user", "Запрос: {query}")
#])
prompt_short = ChatPromptTemplate.from_messages([
    ("system", (
        "Ты — ИИ-инженер ИТ-поддержки завода Омский каучук.\n"
        "Твоя задача — выдать КРАТКОЕ, строго тезисное ИТ-решение для всплывающей подсказки оператора (3-4 лаконичных пункта).\n\n"
        "КРИТИЧЕСКИЕ ЗАПРЕТЫ:\n"
        "- ЗАПРЕЩЕНО выводить фразы вроде 'Официальный ответ по ИТ-инциденту' или 'Заявка №'.\n"
        "- ЗАПРЕЩЕНО придумывать номера заявок, писать приветствия, вводные слова или подписи.\n"
        "- Начинай ответ СРАЗУ с первого технического пункта действий.\n\n"
        "Контекст из регламентов завода:\n{context}"
    )),
    ("user", "Запрос: {query}")
])

# СЛОЙ 3: Генератор полных ответов (для вебхука в тикет)
#prompt_full = ChatPromptTemplate.from_messages([
#    ("system", (
#        "Ты — ведущий ИИ-специалист технической поддержки завода Омский каучук.\n"
#        "Сформируй развернутый, глубокий официальный ответ по ИТ-инциденту для фиксации в истории заявки.\n"
#        "Опиши возможные технические причины неисправности и дай детальные инструкции по ее устранению.\n"
#        "Оформляй структуру красиво, используя заголовки Markdown (### или ####) и нумерованные списки.\n\n"
#        "Контекст из базы знаний завода:\n{context}"
#    )),
#    ("user", "Заявка: {query}")
#])
# ==========================================
# СЛОЙ 3: Исправленный генератор полных ответов (БЕЗ ГАЛЛЮЦИНАЦИЙ И ПОВТОРОВ)
# ==========================================
prompt_full = ChatPromptTemplate.from_messages([
    ("system", (
        "Ты — ведущий ИИ-специалист технической поддержки завода Омский каучук.\n"
        "Сформируй развернутый технический разбор ИТ-проблемы для фиксации в истории заявки.\n\n"
        "КРИТИЧЕСКИЕ ЗАПРЕТЫ:\n"
        "- КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать шапки, заголовки и строки вида 'Официальный ответ по ИТ-инциденту' или 'Заявка №'.\n"
        "- ЗАПРЕЩЕНО генерировать или выдумывать номера инцидентов, дату, время, имя оператора или заявителя.\n"
        "- Не пиши никаких вводных фраз и приветствий.\n\n"
        "ТРЕБОВАНИЯ К СТРУКТУРЕ (начинай сразу с сути):\n"
        "1. Возможные причины неисправности (кратко перечисли технические причины).\n"
        "2. Пошаговая инструкция по устранению (детальные технические шаги для инженера).\n\n"
        "Оформляй структуру строго через заголовки Markdown (### или ####) и нумерованные списки.\n\n"
        "Контекст из базы знаний завода:\n{context}"
    )),
    ("user", "Заявка: {query}")
])

chain_classifier = prompt_classifier | llm | StrOutputParser()
chain_short = prompt_short | llm | StrOutputParser()
chain_full = prompt_full | llm | StrOutputParser()

# ==========================================
# 5. API ЭНДПОИНТЫ
# ==========================================

@app.post("/api/v1/chat")
async def chat_assistant(request: Request):
    try:
        data = await request.json()
        user_text = data.get("text", "").strip()
        
        # Первичный отсекатель по длине
        if not user_text or len(user_text) < 6: 
            return {"response": "ДАННЫЕ_НЕ_НАЙДЕНЫ", "sources": []}

        safe_query = mask_personal_data(user_text)
        
        # ЭТАП 1: Классификация запроса на ИТ/Офтоп
        classification = await chain_classifier.ainvoke({"query": safe_query})
        classification = classification.strip()
        
        print(f"[Guardrail Classifier] Запрос: '{safe_query}' -> Результат: {classification}")
        
        # Защита от пробития фильтра: если в ответе нет явной '1' или есть признаки '0'
        if "1" not in classification or classification.startswith("0"):
            return {"response": "ДАННЫЕ_НЕ_НАЙДЕНЫ", "sources": []}

        # ЭТАП 2: Поиск совпадений в Qdrant
        context, sources_data = extract_context_and_sources(safe_query)
        
        # Если в Qdrant пусто, подменяем контекст жестким указанием, исключающим галлюцинации
        if not context.strip():
            context = "В официальных инструкциях завода нет прямого совпадения. Дай стандартную общую рекомендацию по решению данной ИТ-проблемы."
            sources_data = []
            
        # ЭТАП 3: Генерация краткого ответа
        ai_answer = await chain_short.ainvoke({"context": context, "query": safe_query})
        
        if "ДАННЫЕ_НЕ_НАЙДЕНЫ" in ai_answer:
            return {"response": "ДАННЫЕ_НЕ_НАЙДЕНЫ", "sources": []}

        return {"response": ai_answer, "sources": sources_data}
        
    except Exception as e:
        print(f"[API ERROR] Ошибка в блоке инвайрона: {e}")
        return {"response": "ДАННЫЕ_НЕ_НАЙДЕНЫ", "sources": []}


@app.post("/api/v1/glpi-webhook")
async def handle_glpi_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception: return {"status": "error"}

    event_data = payload.get("event_data", {})
    ticket_id = event_data.get("id")
    user_query = event_data.get("content")

    if not ticket_id or not user_query: return {"status": "ignored"}

    safe_query = mask_personal_data(user_query)
    
    # Вебхук также защищаем классификатором от случайного спама
    classification = await chain_classifier.ainvoke({"query": safe_query})
    if "1" not in classification.strip():
        print(f"[Webhook Guard] Тикет #{ticket_id} пропущен: не относится к ИТ.")
        return {"status": "skipped"}

    context, sources = extract_context_and_sources(safe_query)
    ai_response = await chain_full.ainvoke({"context": context, "query": safe_query})

    if "ДАННЫЕ_НЕ_НАЙДЕНЫ" in ai_response or len(ai_response.strip()) < 15:
        return {"status": "skipped"}

    post_solution_to_glpi(ticket_id, ai_response, sources)
    return {"status": "success", "ticket_id": ticket_id}


@app.post("/api/v1/create-ticket")
async def api_create_ticket(request: Request):
    try:
        data = await request.json()
        raw_text = data.get("text", "").strip()
        glpi_user_id = data.get("user_id") 
        
        if not raw_text: raise HTTPException(status_code=400, detail="Текст заявки пуст")
            
        safe_text = mask_personal_data(raw_text)
        ticket_id = create_ticket_via_api(title=raw_text, content=safe_text, glpi_user_id=glpi_user_id)
        
        if ticket_id > 0: return {"status": "success", "ticket_id": ticket_id}
        return {"status": "error", "message": "Ошибка записи тикета в базу GLPI"}
    except Exception as e: 
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
