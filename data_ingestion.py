# Скрипт парсинга регламентов (Unstructured)
import os
# Импортируем загрузчики для разных форматов
from langchain_community.document_loaders import TextLoader, PyPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

OLLAMA_BASE_URL = "http://192.168.222.66:11434"
QDRANT_URL = "http://192.168.222.66:6333"
COLLECTION_NAME = "factory_regulations"
REGULATIONS_DIR = "./rag_data"

def get_loader_for_file(file_path: str):
    """Автоматически выбирает нужный класс загрузчика по расширению файла"""
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.txt':
        return TextLoader(file_path, encoding='utf-8')
    elif ext == '.pdf':
        return PyPDFLoader(file_path)
    elif ext == '.docx' or ext == '.doc':
        return Docx2txtLoader(file_path)
    else:
        return None # Неподдерживаемый формат

def main():
    if not os.path.exists(REGULATIONS_DIR):
        os.makedirs(REGULATIONS_DIR)
        print(f"[*] Создана папка '{REGULATIONS_DIR}'. Сложите туда инструкции и запустите скрипт заново.")
        return

    # Теперь ищем любые текстовые, PDF или Word файлы
    valid_extensions = ('.txt', '.pdf', '.docx', '.doc')
    files = [f for f in os.listdir(REGULATIONS_DIR) if f.lower().endswith(valid_extensions)]
    
    if not files:
        print(f"[-] В папке '{REGULATIONS_DIR}' нет подходящих файлов {valid_extensions}")
        return

    print(f"[+] Найдено файлов для импорта: {len(files)}")

    print("[*] Инициализация модели эмбеддингов bge-m3...")
    embeddings = OllamaEmbeddings(base_url=OLLAMA_BASE_URL, model="bge-m3:latest")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    all_chunks = []

    for file_name in files:
        file_path = os.path.join(REGULATIONS_DIR, file_name)
        print(f"[*] Парсинг файла: {file_name}...")
        
        # Определяем подходящий загрузчик
        loader = get_loader_for_file(file_path)
        if not loader:
            print(f"[!] Пропуск файла {file_name}: неподдерживаемый формат.")
            continue

        try:
            # Загружаем документ (LangChain сам извлечет чистый текст из PDF/Word)
            documents = loader.load()
            
            # Нарезаем на чанки
            chunks = text_splitter.split_documents(documents)
            
            for chunk in chunks:
                chunk.metadata["source_file"] = file_name
                
            all_chunks.extend(chunks)
            print(f"[+] Файл успешно обработан. Создано чанков: {len(chunks)}")
        except Exception as e:
            print(f"[-] Ошибка при обработке файла {file_name}: {e}")

    if not all_chunks:
        print("[-] Нет данных для загрузки в Qdrant.")
        return

    print(f"[+] Подготовлено всего чанков: {len(all_chunks)}")
    print("[*] Отправка векторов в Qdrant...")
    
    try:
        qdrant_store = QdrantVectorStore.from_documents(
            documents=all_chunks,
            embedding=embeddings,
            url=QDRANT_URL,
            collection_name=COLLECTION_NAME
        )
        print(f"[SUCCESS] База данных Qdrant успешно обновлена!")
    except Exception as e:
        print(f"[-] Ошибка загрузки в Qdrant: {e}")

if __name__ == "__main__":
    main()
