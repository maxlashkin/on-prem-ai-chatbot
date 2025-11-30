# on-prem-ai-chatbot
# Чат-бот службы ИТ поддержки на предприятии
```mermaid
graph TB
    %% Определение стилей
    classDef user fill:#E1F5FE,stroke:#0277BD,stroke-width:2px,rx:10,ry:10;
    classDef app fill:#FFF9C4,stroke:#FBC02D,stroke-width:2px,rx:5,ry:5;
    classDef ai fill:#E1BEE7,stroke:#7B1FA2,stroke-width:2px,rx:5,ry:5;
    classDef db fill:#E0E0E0,stroke:#616161,stroke-width:2px;
    classDef ext fill:#FFCCBC,stroke:#D84315,stroke-width:2px;

    subgraph User_Environment[Среда Пользователя]
        U1(ПК в Офисе):::user
        U2(Планшет в Цехе):::user
    end

    subgraph DMZ_Layer[Слой Приложений (CPU Server)]
        LB[Load Balancer / Gateway]:::app
        Auth[Auth Service<br/>SSO]:::app
        Sanitizer[PII Sanitizer<br/>Очистка данных]:::app
        Orch[AI Orchestrator<br/>Python/LangChain]:::app
    end

    subgraph Secure_Zone[Защищенный Контур ИИ (GPU Server)]
        subgraph AI_Core[AI Engine]
            LLM[LLM Server<br/>vLLM/Ollama]:::ai
            Embed[Embedding Model]:::ai
        end
        
        subgraph Knowledge_Base[Data Layer]
            VecDB[(Vector DB<br/>Qdrant)]:::db
            Cache[(Redis Cache)]:::db
        end
    end

    subgraph Corporate_Infra[Корпоративная Инфраструктура]
        AD[(Active Directory)]:::ext
        ITSM[(ITSM System<br/>Jira/Naumen)]:::ext
        Zabbix[(Monitoring<br/>Zabbix)]:::ext
    end

    %% Потоки данных
    U1 -->|HTTPS / REST| LB
    U2 -->|HTTPS / REST| LB

    LB -->|1. Auth Check| Auth
    LB -->|2. Secure Route| Sanitizer
    Sanitizer -->|3. Clean Text| Orch

    Orch <-->|4. RAG Search| VecDB
    Orch -->|5. Inference Request| LLM
    LLM -->|6. Generated Text| Orch

    Orch -->|Action: Create Ticket| ITSM
    Orch -->|Action: User Check| AD
    Orch -->|Action: Check Status| Zabbix

    %% Связи внутри AI
    Embed -.->|Vectorize| VecDB
    LLM -.->|Uses GPU| AI_Core
```mermaid
