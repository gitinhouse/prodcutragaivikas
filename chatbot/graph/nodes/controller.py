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
        if p.lower() in query.lower(): return p
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

    # ── OUT OF SCOPE ──────────────────────────
    if intent == "out_of_scope":
        return {**base, "action_type": "info", "cta_intent": "recovery"}

    # ── THANK YOU ─────────────────────────────
    if intent == "thank_you":
        return {**base, "action_type": "info", "cta_intent": "final_thank_you"}

    # ── PRODUCT SEARCH ────────────────────────
    if intent == "product_search":
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
            updated_state["resolved_product"] = matched
            updated_state["sales_stage"] = "closing"
            # LOYALTY GUARD
            target_cta = "ask_lead_info" if not has_lead else "confirm_order_on_file"
            return {**base, "action_type": "recommend", "cta_intent": target_cta,
                    "context_payload": {"selected_product": matched}}
        return {**base, "action_type": "recommend", "cta_intent": "show_options"}

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
    return {**base, "action_type": "info", "cta_intent": "clarify"}

async def controller_node(state: GraphState):
    user_query = state.get("sanitized_input", state.get("last_user_query", "")).lower()
    full_history = state.get("messages", [])

    # 1. LLM CLASSIFICATION (Restore Search Intelligence)
    llm = get_llm()
    try:
        raw_response = await llm.ainvoke([
            {"role": "system", "content": CLASSIFIER_PROMPT},
            *(full_history[-6:])
        ])
        raw_text = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)
        cleaned = re.sub(r"```(?:json)?", "", raw_text).strip().strip("`").strip()
        json_match = re.search(r'(\{.*\})', cleaned, re.DOTALL)
        result = json.loads(json_match.group(1)) if json_match else {}
    except:
        result = {"intent": "product_search"}

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
    elif is_short_confirm or bool(re.search(r"\b(20\d{2}|audi|bmw|civic|honda|mercedes)\b", user_query)):
        # Only override to search if we aren't already in a purchase flow
        if result.get("intent") != "purchase_intent":
            result["intent"] = "product_search"
    
    # 3. CONTEXTUAL LEAD CONFIRMATION (e.g. "same email", "on file", "wait")
    elif bool(re.search(r"\b(same email|on file|already gave|you have it|wait|hold on|stop)\b", user_query)) and state.get("has_email"):
        result["intent"] = "purchase_intent"
        result["is_contextual"] = True

    # 3. DOMAIN LOCK
    if result.get("category") == "tires" and not bool(re.search(r"\b(wheel|rim)\b", user_query)):
        return {**state, "action_type": "hard_block", "cta_intent": "redirect_to_domain"}

    # 4. EXECUTE
    state_updates = StateManager.process_state(state, result, user_query)
    
    # Update temporary state for routing logic
    temp_state = {**state, **state_updates}
    routing = _route(result["intent"], state, result, temp_state, user_query)

    return {**state_updates, **routing}
