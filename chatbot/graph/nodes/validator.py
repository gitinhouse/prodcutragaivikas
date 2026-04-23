import re
import logging
from chatbot.graph.state import GraphState

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.validator")

async def validator_node(state: GraphState):
    """
    INGRESS SYNC: Dumb Input Cleaner.
    This node is responsible ONLY for synchronizing the latest message 
    into the state and cleaning whitespace. 
    It makes ZERO business or domain decisions.
    """
    # 0. INGRESS SYNCHRONIZATION (CRITICAL)
    messages = state.get("messages", [])
    raw_query = messages[-1].content if messages else ""
    user_query = raw_query.strip()
    
    # 1. EMAIL EXTRACTION (PERMANENCE)
    # Scan for email pattern to lock it into the state
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', user_query)
    current_email = state.get("customer_email")
    new_email = email_match.group(0) if email_match else current_email
    
    logger.info(f"Validator: Ingress='{user_query}' Lead='{new_email}'")
    
    # Update state (The delta will be merged)
    return {
        "last_user_query": raw_query,
        "sanitized_input": user_query.lower(),
        "customer_email": new_email,
        "has_email": bool(new_email)
    }
