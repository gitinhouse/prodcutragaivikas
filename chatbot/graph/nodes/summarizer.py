import logging
from langchain_core.messages import SystemMessage, HumanMessage, RemoveMessage
from chatbot.graph.state import GraphState
from config.llm_config import get_llm
from chatbot.helpers.prompts import SUMMARIZER_PROMPT

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.summarizer")

async def summarizer_node(state: GraphState):
    """
    SEMANTIC MEMORY SUMMARIZER V1.
    Distills long-term history into a persistent 'summary' state.
    Prunes the message history to save tokens and maintain focus.
    """
    messages = state.get("messages", [])
    existing_summary = state.get("summary", "")
    
    # TRIGGER: Only summarize if history is getting long (e.g., > 10 messages / 5 turns)
    if len(messages) <= 10:
        return {}

    logger.info(f"Summarizer: Compressing {len(messages)} messages into Milestone Memory.")
    
    # 1. PREPARE SUMMARIZATION PROMPT
    # Default empty JSON for first run
    default_json = '{"first_query": "None", "vehicle_history": [], "current_vehicle": "None", "preferences": {"color": "None", "style": "None", "budget": "None", "notes": []}, "current_stage_summary": "None", "last_user_intent": "None"}'
    
    # We take all but the last 2 messages (the immediate context) for summarization
    messages_to_summarize = messages[:-2]
    msg_history_str = "\n".join([f"{m.type.upper()}: {m.content}" for m in messages_to_summarize])
    
    summary_instruction = SUMMARIZER_PROMPT.format(
        existing_summary=existing_summary or default_json,
        messages=msg_history_str
    )

    # 2. CALL LLM
    llm = get_llm()
    
    response = await llm.ainvoke([
        SystemMessage(content=summary_instruction)
    ])
    
    # 3. CLEAN & PARSE (Simple cleanup for JSON)
    new_summary = response.content.replace("```json", "").replace("```", "").strip()

    # 4. PRUNE HISTORY
    delete_messages = [RemoveMessage(id=m.id) for m in messages_to_summarize if hasattr(m, 'id')]
    
    logger.info("Summarizer: Structured Memory updated. Pruning old raw messages.")
    
    return {
        "summary": new_summary,
        "messages": delete_messages
    }
