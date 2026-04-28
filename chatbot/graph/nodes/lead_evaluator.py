import logging
from chatbot.graph.state import GraphState, Intent

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.lead_evaluator")

async def lead_evaluator_node(state: GraphState):
    """
    STRATEGY ENGINE: The Decision Node (Elite Layer).
    Evaluates Action Node results and applies advanced Sales Intelligence.
    """
    intent = state.get("intent")
    intent_str = str(intent.value if hasattr(intent, "value") else intent).lower()
    user_query = state.get("last_user_query", "").lower()
    user_stage = state.get("sales_stage", "discovery")
    domain = state.get("domain", "in_scope")
    raw_data = state.get("raw_response_data", {})
    action_type = raw_data.get("action", "discovery")
    
    vehicle_context = state.get("vehicle_context", {})
    entities = state.get("extracted_entities", {})
    has_email = bool(state.get("customer_email") or state.get("has_email", False))
    history = state.get("advisor_history", [])

    logger.info(f"Lead Evaluator: Analyzing Strategy (Stage={user_stage}, Intent={intent_str})")

    # --- 1. SIGNAL DETECTION ---
    is_engaged = any(k in user_query for k in ["show", "options", "what do you have", "recommend", "looking", "rims", "wheels", "list"])
    has_price_intent = any(k in user_query for k in ["price", "cost", "how much", "total", "quote", "pricing"])
    has_hesitation = intent_str == "hesitant" or any(k in user_query for k in ["expensive", "too much", "high", "cheaper"])
    is_buying = intent_str == "purchase_intent" or any(k in user_query for k in ["buy", "order", "take it", "checkout"])

    # --- 2. THE STRATEGY MATRIX ---
    # --- RULE: RESPECT CONTROLLER'S DECISION (UNLESS ACTION FAILED) ---
    # If the Controller set show_options but Recommender found nothing, we MUST pivot.
    controller_intent = state.get("cta_intent", "")
    PASS_THROUGH_INTENTS = ["show_options", "ask_lead_info", "redirect_to_domain", "clarify", "recovery", "final_thank_you", "ask_vehicle", "no_results", "fitment_summary", "brand_inquiry", "product_detail", "info", "greeting"]
    
    if controller_intent in PASS_THROUGH_INTENTS and action_type != "no_fitment_found":
        logger.info(f"Lead Evaluator: Passing through Controller strategy '{controller_intent}'.")
        raw_data["allow_lead_capture"] = (controller_intent == "ask_lead_info")
        raw_data["cta_intent"] = controller_intent
        return {"cta_intent": controller_intent, "raw_response_data": raw_data}

    cta_intent = "ask_vehicle"  # Default fallback only if controller gave nothing useful

    # A. DOMAIN PROTECTION
    if domain == "hard_out":
        cta_intent = "redirect_to_domain"

    # B. NO FITMENT FOUND
    elif action_type == "no_fitment_found":
        if not vehicle_context.get("year"):
            cta_intent = "ask_vehicle"
        else:
            cta_intent = "no_results"

    # C. PURE DISCOVERY (no vehicle at all)
    elif user_stage == "discovery":
        if not (vehicle_context.get("make") and vehicle_context.get("model") and vehicle_context.get("year")):
            cta_intent = "ask_vehicle"
        else:
            cta_intent = "show_options"

    # D. DECISION NODE: Advanced Sales Intelligence
    elif user_stage in ["guided_discovery", "recommend", "partial_recommend", "recommendation", "fitment"]:
        total_results = raw_data.get("total_results", 0)
        
        if has_price_intent:
            cta_intent = "offer_quote"
        elif has_hesitation:
            cta_intent = "reduce_friction"
        elif total_results > 3 and action_type == "recommend":
            logger.info("Decision Node: High results volume detected. Triggering comparison upsell.")
            cta_intent = "suggest_comparison"
        else:
            cta_intent = "show_options"

    # E. CLOSING
    elif user_stage == "closing" or is_buying:
        if has_email:
            cta_intent = "close"
        else:
            cta_intent = "ask_lead_info"

    # --- LEAD CAPTURE PERMISSION ---
    allow_lead = cta_intent in ["offer_quote", "soft_close", "close", "ask_lead_info"]

    logger.info(f"Lead Evaluator FINAL Strategy: '{cta_intent}' (AllowLead={allow_lead})")

    raw_data["allow_lead_capture"] = allow_lead
    raw_data["cta_intent"] = cta_intent

    return {
        "cta_intent": cta_intent,
        "raw_response_data": raw_data
    }
