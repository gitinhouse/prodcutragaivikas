# Sales AI - High-Performance Conversational Advisor

A production-grade, stateful sales chatbot built with **Django**, **LangGraph**, and **OpenAI**. Architected for low latency, high trust, and a natural "Human Advisor" feel.

---

## 🚀 Key Features

*   **Single-Stream Architecture**: Eliminates the "Double LLM Call" bottleneck. Action nodes produce structured technical metadata, and a dedicated `Response_generator` synthesizes it once into a flowing, typewriter-streamed response.
*   **Trust-Locked Product Retrieval**: Hybrid search engine combining exact SKU matching, technical specification filtering (Diameter, Price, Bolt Pattern), and vector similarity.
*   **Human-Advisor Persona**: Hardened prompts that guide users through discovery and lead capture without robotic "walls of text" or pushy system language.
*   **Stateful Memory**: Persistent conversation threads backed by **PostgreSQL** (via `langgraph-checkpoint-postgres`), ensuring a user's budget and preferences are remembered across reloads.
*   **Simulated Streaming**: Static responses (like greetings) are manually chunked to maintain a consistent "typewriter" UI effect for the user.

---

## 🧩 Conversational Flow

The AI follows a non-linear, intent-driven graph:

1.  **Intent Classification**: Every message is categorized (Query, Hesitancy, Purchase Intent, etc.) using Pydantic-driven structured output.
2.  **Logic Routing**:
    *   **Browsing**: Routes to `discovery_node` for smart follow-up questions.
    *   **Searching**: Routes to `recommender_node` for product comparisons.
    *   **Buying**: Routes to `lead_capture_node` (Natural closing).
    *   **Objection**: Routes to `hesitation_node` (Empathetic resolution).
3.  **Synthesis**: Data is piped to the `Response_generator` which produces a single, cohesive paragraph under 60 words.
4.  **Lead Lock**: Built-in "Exit Strategy" detects rejection and releases the lead-capture lock if a user doesn't want to share their email.

---

## 🛠️ Tech Stack

*   **Backend**: Python / Django
*   **Orchestration**: LangGraph (State Machine)
*   **Intelligence**: OpenAI GPT-4o / Text-Embedding-3
*   **Database**: PostgreSQL (Vector Storage + Checkpoints)
*   **Real-time**: SSE (Server-Sent Events) via Daphne ASGI
*   **Cache**: Redis

---

## 📂 Key Files

*   `chatbot/graph/graph.py`: The core state machine and node definitions.
*   `chatbot/graph/nodes/`: Specialized logic for classification, search, and lead capture.
*   `chatbot/helpers/prompts.py`: The "Human Advisor" prompt repository and global rules.
*   `chatbot/services/stream_service.py`: SSE logic and simulated typewriter streaming.
*   `chatbot/services/product_service.py`: The hybrid search retrieval engine.

---

## 🏁 Getting Started

1.  Ensure Docker and Docker Compose are installed.
2.  Create a `.env` file with your `OPENAI_API_KEY`.
3.  Run the stack:
    ```bash
    docker-compose up --build
    ```
4.  Access the chat interface at `http://localhost:8000`.
