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
```


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
```
Рис. 3. Алгоритм работы модуля классификации интентов (Intent Router)
```plantuml
@startuml
skinparam monochrome true
skinparam shadowing false

start

:Прием очищенного текста от PII Sanitizer;
:Формирование Few-Shot промпта\n(передача примеров интентов под специфику завода);
:Запрос к локальной модели Saiga Llama-3\nс фиксацией JSON-структуры ответа;

:Инференс модели и генерация JSON-пакета;
:Парсинг JSON-ответа\n(извлечение полей selected_intent и confidence_score);

if (Показатель уверенности (confidence_score) >= 0.75?) then (Да)
    if (Какой класс выбран в selected_intent?) then (technical_issue)
        :Направление в контур RAG Pipeline;
        :Семантический поиск по регламентам ИТ в Qdrant;
        :Синтез ответа на основе инструкций;
    else (greeting / chitchat)
        :Обход баз данных;
        :Генерация вежливого базового ответа;
    endif
else (Нет: confidence_score < 0.75)
    :Классификация признана неуверенной;
    :Присвоение класса 'out_of_scope' / 'unclear';
    :Формирование JSON-пакета для отправки в ITSM (GLPI);
    :Автоматическое создание тикета на инженера поддержки;
    :Вывод уведомления: "Передаю ваш запрос специалисту";
endif

:Передача сформированного текста на демаскирование;
stop
@enduml
```



```plantuml
@startuml
start
:Получение регламента/инструкции (PDF/Docx);
partition "Предобработка" {
  :Парсинг текста из документа;
  :Разбиение на фрагменты (Chunking);
  note right: Например, по 500 символов\nс перекрытием в 10%
}
partition "Векторизация" {
  :Отправка чанков в Embedding-модель;
  :Получение векторных представлений;
}
partition "Хранение" {
  :Запись векторов в Qdrant;
  :Привязка метаданных\n(номер приказа, раздел, дата);
}
if (Ошибки при индексации?) then (да)
  :Логирование ошибки;
  :Уведомление администратора;
else (нет)
  :Статус: "Документ доступен для поиска";
endif
stop
@enduml
```

Взаимодейстивие с пользователем 

```plantuml
@startuml
actor "Сотрудник завода" as User
participant "Интерфейс чат-бота" as UI
participant "PII Sanitizer" as Sanitizer
participant "Embedding Model" as Embedder
participant "Qdrant (Vector DB)" as VectorDB
participant "Local LLM" as LLM

User -> UI: Задает вопрос по регламенту
UI -> Sanitizer: Передает текст запроса
Sanitizer -> Sanitizer: Маскирует ПДн (ФИО, телефоны)
Sanitizer -> Embedder: Чистый текст запроса
Embedder -> Embedder: Генерация вектора запроса
Embedder -> VectorDB: Поиск похожих фрагментов (регламентов)
VectorDB -> Embedder: Возвращает топ-N фрагментов текста
Embedder -> LLM: Промпт: [Контекст из БЗ] + [Вопрос]
LLM -> LLM: Генерация ответа с цитированием
LLM -> UI: Готовый ответ пользователю
UI -> User: Отображает инструкцию
@enduml
```
