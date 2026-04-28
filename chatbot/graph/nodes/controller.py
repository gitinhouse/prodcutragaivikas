import re
import json
import logging
from chatbot.graph.state import GraphState
from chatbot.helpers.state_manager import StateManager
from chatbot.helpers.constants import DomainTypes
from chatbot.helpers.prompts import CLASSIFIER_PROMPT
from config.llm_config import get_llm

logger = logging.getLogger("chatbot.nodes.controller")

def _match_product(query, shown_list, llm_selected=None):
    if not shown_list: return None
    if llm_selected and llm_selected in shown_list: return llm_selected
    for p in shown_list:
        p_low = p.lower()
        q_low = query.lower()
        # Match if the product name is in the query, OR if the query contains the core model name (min 5 chars)
        if p_low in q_low or (len(q_low) > 8 and q_low in p_low): return p
    return None

def _route(intent, state, result, updated_state, user_query):
    # Context retrieval
    sales_stage = updated_state.get("sales_stage", "discovery")
    vehicle_context = updated_state.get("vehicle_context", {})
    vehicle_locked = updated_state.get("vehicle_locked", False)
    shown_products = updated_state.get("shown_products", [])
    resolved_product = updated_state.get("resolved_product")
    has_lead = bool(state.get("customer_email") or state.get("has_email"))
    
    # LLM matched product (if any)
    llm_selected = result.get("selected_product")
    context_ref = result.get("context_ref")
    is_contextual = result.get("is_contextual", False)

    base = {
        "intent": intent,
        "is_contextual": is_contextual,
        "context_ref": context_ref,
        "action_type": "info", 
        "cta_intent": "clarify"
    }

    # ── GREETINGS ─────────────────────────────
    if intent == "greeting":
        return {**base, "action_type": "info", "cta_intent": "greeting"}

    # ── CONFIDENCE GUARD (Pre-Frontal Cortex) ──
    confidence = result.get("confidence", 1.0)
    missing = result.get("missing_fields", [])
    if confidence < 0.50 or (any("vehicle" in m for m in missing) and intent in ["fitment_lookup", "recommendation"]):
        logger.info(f"Controller: Low confidence ({confidence}) or missing fields {missing}. Triggering clarification.")
        return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}

    # ── OUT OF SCOPE ──────────────────────────
    if intent == "out_of_scope":
        return {**base, "action_type": "info", "cta_intent": "recovery"}

    # ── THANK YOU ─────────────────────────────
    if intent == "thank_you":
        return {**base, "action_type": "info", "cta_intent": "final_thank_you"}
        
    # ── FITMENT CHECK ─────────────────────────
    if intent == "fitment_check":
        if vehicle_locked:
            return {**base, "action_type": "fitment_validation", "cta_intent": "fitment_summary"}
        return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}

    # ── PRODUCT SEARCH / FITMENT LOOKUP / RECOMMENDATION ──
    if intent in ["product_search", "fitment_lookup", "recommendation"]:
        if vehicle_locked:
            return {**base, "action_type": "recommend", "cta_intent": "show_options"}
        else:
            return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}

    # ── PURCHASE INTENT ───────────────────────
    if intent == "purchase_intent":
        if not shown_products:
            # If they try to buy but we haven't shown anything, don't hallucinate.
            return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}
            
        matched = _match_product(user_query, shown_products, llm_selected)
        if matched:
            # LOYALTY GUARD
            target_cta = "ask_lead_info" if not has_lead else "confirm_order_on_file"
            return {**base, "action_type": "recommend", "cta_intent": target_cta,
                    "context_payload": {"selected_product": matched},
                    "resolved_product": matched,
                    "sales_stage": "closing"}
            
        if vehicle_locked:
            return {**base, "action_type": "recommend", "cta_intent": "show_options"}
        return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}

    # ── BRAND INQUIRY ─────────────────────────
    if intent == "brand_inquiry":
        return {**base, "action_type": "info", "cta_intent": "brand_inquiry"}

    # ── PRODUCT DETAIL ────────────────────────
    if intent == "product_detail" or (intent == "info_request" and is_contextual):
        about = resolved_product or (shown_products[0] if shown_products else None)
        # If the user asks for details but we can't identify WHICH wheel (half message)
        if not about and not llm_selected:
            return {**base, "action_type": "info", "cta_intent": "clarify_product"}
            
        return {**base, "action_type": "info", "cta_intent": "product_detail",
                "context_payload": {"about_product": about}}

    # ── FALLBACK ──────────────────────────────
    if vehicle_locked:
        return {**base, "action_type": "recommend", "cta_intent": "show_options"}
    return {**base, "action_type": "discovery", "cta_intent": "ask_vehicle"}

async def controller_node(state: GraphState):
    user_query = state.get("sanitized_input", state.get("last_user_query", "")).lower()
    full_history = state.get("messages", [])

    # 1. LLM CLASSIFICATION (Structured Intelligence)
    from chatbot.graph.schemas import ControllerSchema
    llm = get_llm()
    try:
        structured_llm = llm.with_structured_output(ControllerSchema)
        raw_result = await structured_llm.ainvoke([
            {"role": "system", "content": CLASSIFIER_PROMPT},
            *(full_history[-6:])
        ])
        # Convert Pydantic model to dict for downstream logic compatibility
        result = raw_result.model_dump()
    except Exception as e:
        logger.error(f"Controller: Structured Output failed: {e}")
        result = {"intent": "product_search", "category": "wheels", "attributes": {}}

    # Apply Defaults
    result.setdefault("intent", "product_search")
    result.setdefault("category", "wheels")
    
    # 2. DETERMINISTIC OVERRIDES (Surgical Fixes)
    # ONLY trigger for short, clear confirmations to avoid hijacking "okay i will buy it"
    confirm_patterns = r"(?i)^(yes|correct|yep|yeah|that's it|exactly|confirm|yes it is|it is correct)$"
    is_short_confirm = bool(re.search(confirm_patterns, user_query.strip()))
    is_thanks = bool(re.search(r"\b(thank|thanks|thx|ty|grateful)\b", user_query))
    
    if is_thanks:
        result["intent"] = "thank_you"
    elif bool(re.search(r"\b(20\d{2}|audi|bmw|civic|honda|mercedes|tesla|toyota|jeep|ford|chevy|dodge|ram|maruti|suzuki|tata|mahindra)\b", user_query)) or bool(re.search(r"\$\d+|under \d+|budget", user_query)):
        # Only override to search if we aren't already in a purchase flow
        if result.get("intent") not in ["purchase_intent", "product_detail"]:
            result["intent"] = "product_search"
    
    # 2.5 SMART CONFIRMATION (Prevent 'Ok' Trap)
    # If user says 'ok' or 'yes', only treat as purchase if:
    # 1. A product is ALREADY resolved
    # 2. The bot DID NOT just ask if the user wants to explore more/others
    last_cta = state.get("cta_intent", "")
    last_action = state.get("last_action", "")
    
    # These CTAs indicate the bot is offering MORE options, so 'yes' means 'show me more'
    is_offering_more = last_cta in ["show_options", "clarify_product"] or last_action in ["no_fitment_found", "out_of_stock"]

    if is_short_confirm:
        if state.get("resolved_product") and not is_offering_more:
            result["intent"] = "purchase_intent"
        else:
            # If we were offering more, 'yes' maps to show_more_options
            result["intent"] = "show_more_options" if is_offering_more else "info_request"
            result["is_contextual"] = True
    
    # 3. CONTEXTUAL LEAD & DETAIL OVERRIDES
    has_details_intent = bool(re.search(r"\b(detail|specs|specification|more on|tell me about|how many|available|stock|price|cost)\b", user_query))
    matched_context_product = _match_product(user_query, state.get("shown_products", []))

    if matched_context_product:
        # If they explicitly named an on-screen product, treat it as a product_detail intent
        result["intent"] = "product_detail"
        result["selected_product"] = matched_context_product
        result["is_contextual"] = True
    elif bool(re.search(r"\b(same email|on file|already gave|you have it|wait|hold on|stop)\b", user_query)) and state.get("has_email"):
        result["intent"] = "purchase_intent"
        result["is_contextual"] = True

    # 3.5 MEMORY LAYER: REJECTED PRODUCTS
    rejected_products = state.get("rejected_products", [])
    reject_patterns = r"(?i)\b(don't like|not the|remove|ugly|different|hate|no|don't want)\b"
    if re.search(reject_patterns, user_query):
        matched_reject = _match_product(user_query, state.get("shown_products", []))
        if matched_reject and matched_reject not in rejected_products:
            rejected_products.append(matched_reject)
            logger.info(f"Memory Layer: User rejected '{matched_reject}'")

    # 3.6 DOMAIN LOCK
    if result.get("category") == "tires" and not bool(re.search(r"\b(wheel|rim)\b", user_query)):
        return {**state, "action_type": "hard_block", "cta_intent": "redirect_to_domain"}

    # 4. EXECUTE
    state_updates = StateManager.process_state(state, result, user_query)
    
    # Inject rejected products into state updates
    state_updates["rejected_products"] = rejected_products
    
    # Update temporary state for routing logic
    temp_state = {**state, **state_updates}
    routing = _route(result["intent"], state, result, temp_state, user_query)

    return {**state_updates, **routing}
