Рис. 1. Концептуальная архитектура обработки запросов в локальном ИИ-ассистенте

```plantuml
@startuml
skinparam monochrome true
skinparam shadowing false
start

:Запрос пользователя;
:FastAPI Gateway;
:PII Sanitizer\n(Маскирование ПДн);
:Intent Router\n(Определение намерения);

if (Какой интент обнаружен?) then (Greeting / SmallTalk)
    :Быстрый ответ\n(без обращения к БД);
else (Technical_Issue)
    :RAG-компонент;
    :Векторный поиск (DB)\nчерез Qdrant СУБД;
    :Локальный инференс\n(Saiga Llama-3 / GGUF 4-bit / CPU);
endif

:Формирование ответа\nи демаскирование данных;
:Выдача ответа пользователю;

stop
@enduml
```plantuml


Рис. 2. Процесс прохождения высокоуровневого запроса пользователя через фильтры безопасности, классификатор и RAG-контур.

```plantuml
@startuml
skinparam monochrome true

actor User as "Сотрудник (Цех №3)"
participant API as "FastAPI Gateway"
participant Sanitizer as "PII Sanitizer"
participant Router as "Intent Router"
participant RAG as "RAG Engine (Qdrant)"
database LLM as "LLM Core (Saiga Llama-3)"

User -> API: Текстовое обращение через Web-интерфейс
activate API

API -> Sanitizer: Передача сырого текста на фильтрацию
activate Sanitizer
Sanitizer -> Sanitizer: NER-анализ (SpaCy) + Маскирование ПДн
Sanitizer --> API: Очищенная строка (обезличенный текст)
deactivate Sanitizer

API -> Router: Определение намерения пользователя
activate Router
Router -> Router: Анализ контекста и структуры запроса

alt Намерение: Технический инцидент (Technical_Issue)
    Router -> RAG: Запрос на извлечение контекста (Query Embedding)
    activate RAG
    RAG -> RAG: Семантический поиск по векторам документов
    RAG --> Router: Релевантные фрагменты заводских инструкций
    deactivate RAG
    
    Router -> LLM: Компиляция промпта (Очищенный текст + База знаний)
    activate LLM
    LLM --> API: Генерация технического решения (Ответ-инструкция)
    deactivate LLM

else Намерение: Общее приветствие (Greeting / SmallTalk)
    Router -> LLM: Прямой запрос без обращения к документации
    activate LLM
    LLM --> API: Текст вежливого ответа
    deactivate LLM
end

deactivate Router

API -> Sanitizer: Запрос на обратную подстановку (Демаскирование)
activate Sanitizer
Sanitizer --> API: Финальный персонализированный текст ответа
deactivate Sanitizer

API --> User: Отображение решения в интерфейсе
deactivate API
@enduml
```plantuml
