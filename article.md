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
