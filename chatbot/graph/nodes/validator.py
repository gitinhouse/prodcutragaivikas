import re
import logging
from chatbot.graph.state import GraphState

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.validator")

async def validator_node(state: GraphState):
    """
    SMART IDENTITY LAYER: Extraction & Sync.
    Extracts name and email using structured output to ensure 
    personalized luxury advisory.
    """
    # 0. INGRESS SYNCHRONIZATION
    messages = state.get("messages", [])
    raw_query = messages[-1].content if messages else ""
    user_query = raw_query.strip()
    
    current_name = state.get("customer_name")
    current_email = state.get("customer_email")

    # 1. SMART IDENTITY EXTRACTION (Structured)
    from chatbot.graph.schemas import IdentitySchema
    from config.llm_config import get_llm
    
    # We only trigger the LLM if we are missing information
    new_name = current_name
    new_email = current_email
    
    # Regex fallback for email (extremely fast)
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', user_query)
    if email_match:
        new_email = email_match.group(0)

    # LLM extraction for name and missing email
    if not (new_name and new_email):
        try:
            llm = get_llm()
            structured_llm = llm.with_structured_output(IdentitySchema)
            res = await structured_llm.ainvoke(f"Extract name and email from this message: {user_query}")
            if res.name: new_name = res.name
            if res.email: new_email = res.email
        except Exception as e:
            logger.warning(f"Validator: Identity extraction failed: {e}")

    logger.info(f"Validator: Ingress='{user_query}' Name='{new_name}' Email='{new_email}'")
    
    return {
        "last_user_query": raw_query,
        "sanitized_input": user_query.lower(),
        "customer_name": new_name,
        "customer_email": new_email,
        "has_email": bool(new_email)
    }
