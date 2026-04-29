import json
import logging
import re
from langchain_core.messages import AIMessage
from chatbot.graph.state import GraphState
from chatbot.helpers.constants import SAFE_GREETINGS, STATIC_GREETINGS, DomainTypes, STATIC_MESSAGES
import random
from chatbot.helpers.prompts import SYSTEM_CORE_PROMPT, STRATEGY_TEMPLATES, CONTEXT_BLOCK_TEMPLATE, VARIATION_POOLS
from config.llm_config import get_llm

def get_dynamic_variation(category: str, last_response: str = "") -> str:
    """Selects a random variation from the pool, avoiding direct repetition."""
    pool = VARIATION_POOLS.get(category, [])
    if not pool:
        return "I'm here to help with your build. What's on your mind?"
    
    # Filter out the last response to avoid back-to-back repetition
    valid_options = [v for v in pool if v.strip().lower() not in last_response.strip().lower()]
    return random.choice(valid_options if valid_options else pool)

# MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.synthesizer")

async def synthesizer_node(state: GraphState):
    """
    THE TRUSTED CLOSER V12: Context-Aware Persona.
    Crafts the expert voice based on Phase, Progress, and Strategic Goals.
    """
    phase = state.get("phase", "VEHICLE_COLLECTION")
    cta_intent = state.get("cta_intent", "ask_vehicle")
    full_history = state.get("messages", [])
    last_resp = state.get("last_final_response", "")
    intent = state.get("intent", "")
    
    # 0.5 DATA EXTRACTION (Order Fixed)
    raw_data = state.get("raw_response_data", {})
    action_type = raw_data.get("action", "discovery")
    last_action = state.get("last_action", "")
    debug_info = state.get("debug_info", {})
    
    # 1. ZERO-LATENCY GREETING
    is_greeting = state.get("is_greeting", False)
    if is_greeting and len(full_history) <= 1:
        greeting = random.choice(STATIC_GREETINGS)
        return {"messages": [AIMessage(content=greeting)], "final_response": greeting}

    # 2. FORMAT PRODUCT DATA
    products = raw_data.get("products", [])
    product_info = raw_data.get("product_info", {})
    stock_confirmed = raw_data.get("stock_confirmed", False)
    
    formatted_products = ""
    if cta_intent == "product_detail" and product_info:
        formatted_products = (
            f"WHEEL SPEC SHEET:\n"
            f"- Brand: {product_info.get('brand')}\n"
            f"- Model: {product_info.get('name')}\n"
            f"- Inventory Status: {product_info.get('stock')} units available\n"
            f"- Bolt Pattern: {product_info.get('bolt_pattern')}\n"
            f"- Size: {product_info.get('size')}\n"
            f"- Finish: {product_info.get('finish')}\n"
            f"- Price: ${product_info.get('price')}\n"
            f"- Details: {product_info.get('details')}"
        )
    elif products:
        product_lines = []
        for p in products:
            product_lines.append(f"- **{p.get('marketing_name')}** | ${p.get('price', 'N/A')} ({p.get('stock', 0)} in stock)\n  *Specs: {p.get('finish', 'Premium')} | {p.get('bolt_pattern', 'Verified Fitment')}*")
        formatted_products = "\n".join(product_lines)
    else:
        formatted_products = "[INFO] State: " + debug_info.get("reason", "Standard flow")

    # 3. ASSEMBLY & IMPLICIT PROGRESS
    vehicle_context = state.get("vehicle_context", {})
    vehicle_make = vehicle_context.get("make") or "your vehicle"
    vehicle_name = f"{vehicle_context.get('year','')} {vehicle_make} {vehicle_context.get('model','')}".strip()
    
    # Implicit Progress Language
    progress_phrase = random.choice(VARIATION_POOLS["implicit_progress"]).format(vehicle_make=vehicle_make)
    
    strategy_text = STRATEGY_TEMPLATES.get(cta_intent, STRATEGY_TEMPLATES["clarify"])
    
    context_block = CONTEXT_BLOCK_TEMPLATE.format(
        strategy_text=strategy_text,
        vehicle_type=vehicle_name,
        vehicle_make=vehicle_make,
        vehicle_model=vehicle_context.get("model") or "the vehicle",
        sales_stage=state.get("sales_stage", "discovery"),
        customer_name=state.get("customer_name") or "valued customer",
        customer_contact=state.get("customer_email") or state.get("has_email") or "Not on file",
        stock_confirmed=str(stock_confirmed),
        total_results=raw_data.get("total_results", 0),
        shown_results=len(products),
        last_response=last_resp,
        relaxation_trace=", ".join(raw_data.get("relaxation_steps", [])) if raw_data.get("relaxation_steps") else "None",
        resolved_product=state.get("resolved_product") or "None",
        validation_status=raw_data.get("validation_status", "None"),
        validation_notes=raw_data.get("validation_notes", "None"),
        summary=state.get("summary") or "Conversation just started.",
        product_data=formatted_products
    )
    
    # 4. LLM INVOCATION
    full_system_prompt = f"{SYSTEM_CORE_PROMPT}\n{context_block}\nPROGRESS STATUS: {progress_phrase}"
    synth_history = full_history[-4:] if len(full_history) > 4 else full_history
    
    llm = get_llm()
    full_content = ""
    async for chunk in llm.astream([
        {"role": "system", "content": full_system_prompt},
        *synth_history
    ]):
        full_content += chunk.content

    # 5. STRATEGIC OVERRIDES (Hardening)
    final_output = full_content.strip()

    # A. RE-ENGAGEMENT HOOK (Out-of-Scope Recovery)
    if raw_data.get("apply_reengagement"):
        hook = random.choice(VARIATION_POOLS["reengagement_hook"]).format(vehicle_make=vehicle_make)
        final_output = f"{final_output}\n\n{hook}"

    # B. INTENT ENFORCEMENT
    user_query = state.get("sanitized_input", "").lower()
    is_short_ack = len(user_query.split()) <= 2 and bool(re.search(r"^(ok|cool|nice|good|thanks|yep|yeah|fine)$", user_query.strip()))
    
    if intent == "needs_clarity" or action_type == "pattern_mismatch":
        if action_type == "pattern_mismatch":
            final_output = f"I have exceptional options in that bolt pattern, but they won't fit your {vehicle_make} {vehicle_model}. Technical fitment is our priority—should we stick with the verified matches for your car, or are we working on a different vehicle?"
        else:
            # Schema-Locked Cross Question
            final_output = f"I found some great options for your {vehicle_make}, but I want to narrow them down to your perfect style. Do you have a preferred finish like Black or Silver, or a specific wheel size in mind?"
            
    elif is_short_ack and last_action == "recommend" and state.get("view_count", 0) > 0:
        # Prevent 'OK' Trap (Progressive CTA)
        final_output = f"Excellent choice. Since these are verified for your {vehicle_make}, would you like to see the pricing details, or should we look at a different finish?"
        
    elif cta_intent == "ask_vehicle":
        final_output = get_dynamic_variation("ask_vehicle", last_resp)
    elif cta_intent == "safe_fallback":
        final_output = "I want to ensure your build is perfect. Would you like to continue looking at wheel options for your vehicle, or do you have a specific technical question?"
    elif cta_intent == "close":
        final_output = f"Excellent choice. I've generated your formal technical quote for the {state.get('resolved_product')} and sent it to your email. You should receive it shortly. Would you like to explore other wheel finishes for your {vehicle_make}, or is there anything else I can assist you with today?"
    elif cta_intent == "final_thank_you":
        final_output = f"You're very welcome! It was a pleasure helping you perfect the build for your {vehicle_make}. Your formal quote is in your inbox—feel free to reach out if you have any follow-up questions. Enjoy your new setup!"
    elif cta_intent == "break_loop_with_guidance":
        final_output = f"I've shared quite a few styles! To simplify things, I can narrow this down to the top 3 best-selling options for your {vehicle_make} that I know are in stock. Would you like me to do that?"
    
    return {
        "last_action": action_type if action_type != "pattern_mismatch" else "info",
        "final_response": final_output,
        "last_final_response": final_output
    }
