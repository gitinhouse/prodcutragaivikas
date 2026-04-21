import logging
from chatbot.graph.state import GraphState
from chatbot.helpers.prompts import LEAD_EVALUATOR_PROMPT
from config.llm_config import get_llm

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.lead_evaluator")

async def lead_evaluator_node(state: GraphState):
    """
    Expert Lead Evaluation Node.
    """
    intent = state.get("intent")
    user_query = state.get("last_user_query", "").lower()
    user_stage = state.get("sales_stage", "discovery") # Swapped user_stage for sales_stage
    lead_status = state.get("lead_status", {"attempts": 0, "has_email": False})
    
    # --- POST-CLOSING BEHAVIOR ---
    if user_stage == "post_closing":
        logger.info("Lead Evaluator: Session is in POST-CLOSING stage. Stopping proactive recommendations.")
        raw_data = state.get("raw_response_data", {})
        raw_data["allow_lead_capture"] = False
        raw_data["action"] = "post_closing"
        raw_data["instruction"] = "The sale is closed. Focus ONLY on post-purchase support (order tracking, warranty, session reset). Do not recommend new products."
        return {"raw_response_data": raw_data}

    hesitation_signals = ["budget", "price", "too much", "expensive", "costly", "afford", "cheaper"]
    has_hesitation = any(k in user_query for k in hesitation_signals) or str(intent).lower() == "hesitant"
    
    llm = get_llm()
    
    # 0. THE CORE SALES SAFETY-NET (Prevent False Refusals & Memory Awareness)
    # If the user is talking about 'brands', 'help', 'recommendations', or says 'yes/please', it's ALWAYS wheels.
    sales_affirmations = ["yes", "please", "recommendation", "show", "give", "tell", "more", "look"]
    purchase_signals = ["buy", "purchase", "order", "checkout", "quote", "price on", "how much for"]
    catalog_keywords = ["brand", "catalog", "help", "list", "manufactur", "wheel", "rim"]
    
    is_affirming = any(k in user_query.lower() for k in sales_affirmations)
    is_buying = any(k in user_query.lower() for k in purchase_signals)
    has_catalog_keyword = any(k in user_query.lower() for k in catalog_keywords)

    # PURCHASE LOCK: If they want to buy, don't let the AI guess the intent
    from chatbot.graph.state import Intent
    # 1. SOFT GUARD: If we already have Name AND Email, deny capture to prevent repeats
    has_email = state.get("customer_email") or lead_status.get("has_email")
    has_name = state.get("customer_name")
    
    if has_email and has_name:
        logger.info("Lead Evaluator: Name and Email already present. Disabling further capture attempts.")
        allow_lead = False
    elif has_hesitation:
        logger.warning(f"Lead Evaluator: Hesitation detected for '{user_query}'. Forcing lead capture DENIAL.")
        allow_lead = False
    elif is_buying:
        logger.info(f"Lead Evaluator [SALES LOCK]: High Purchase Intent detected for '{user_query}'.")
        allow_lead = True
    else:
        try:
            result = await llm.ainvoke([
                {"role": "system", "content": LEAD_EVALUATOR_PROMPT},
                {"role": "user", "content": f"Intent: {intent}, Stage: {user_stage}, Status: {lead_status}"}
            ])
            allow_lead = result.get("allow_lead_capture", False)
            logger.info(f"Lead Decision: ALLOWED={allow_lead} | Reason: {result.get('reason')}")
        except Exception:
            logger.error("Lead Evaluator FAILED. Defaulting to deny.")
            allow_lead = False

    raw_data = state.get("raw_response_data", {})
    raw_data["allow_lead_capture"] = allow_lead
    
    return {
        "raw_response_data": raw_data
    }
