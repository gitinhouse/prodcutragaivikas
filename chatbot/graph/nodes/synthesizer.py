import json
import logging
import re
from langchain_core.messages import AIMessage
from chatbot.graph.state import GraphState
from chatbot.helpers.constants import SAFE_GREETINGS, STATIC_GREETINGS, DomainTypes, STATIC_MESSAGES
from chatbot.helpers.prompts import SYNTHESIZER_PROMPT_TEMPLATE
from config.llm_config import get_llm

# MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.synthesizer")

async def synthesizer_node(state: GraphState):
    """
    SUPER-NODE 11: The Trusted Closer.
    Incorporates Live Inventory Status into the expert voice.
    """
    domain = state.get("domain", DomainTypes.IN_SCOPE)
    action_type = state.get("action_type", "discovery")
    cta_intent = state.get("cta_intent", "ask_vehicle")
    sales_stage = state.get("sales_stage", "discovery")
    full_history = state.get("messages", [])
    
    # 1. ZERO-LATENCY GREETING
    is_greeting = state.get("is_greeting", False)
    if is_greeting and len(full_history) <= 1:
        import random
        greeting = random.choice(STATIC_GREETINGS)
        return {"messages": [AIMessage(content=greeting)], "final_response": greeting}

    # 2. FORMAT PRODUCT DATA
    raw_data = state.get("raw_response_data", {})
    products = raw_data.get("products", [])
    product_info = raw_data.get("product_info", {})
    is_relaxed = raw_data.get("is_relaxed_search", False)
    stock_confirmed = raw_data.get("stock_confirmed", False)
    
    formatted_products = ""
    if cta_intent == "product_detail" and product_info:
        # Format spec sheet for detail turn
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
            reason = p.get("ai_reason", "Premium fitment")
            stock = p.get("stock", 0)
            product_lines.append(f"- **{p.get('marketing_name')}** | **${p.get('price', 'N/A')}** ({stock} in stock) — {reason}")
        formatted_products = "\n".join(product_lines)
    else:
        if action_type == "no_fitment_found":
            formatted_products = "[FITMENT_CONFLICT] Technical incompatibility."
        else:
            formatted_products = "[NOT_FOUND] No matches."

    # 3. RENDER TEMPLATE
    attrs = state.get("extracted_entities", {})
    vehicle_context = state.get("vehicle_context", {})
    vehicle_name = f"{vehicle_context.get('year','')} {vehicle_context.get('make','')} {vehicle_context.get('model','')}".strip()
    
    full_system_prompt = SYNTHESIZER_PROMPT_TEMPLATE.format(
        cta_intent=cta_intent,
        sales_stage=sales_stage,
        action_type=action_type,
        vehicle_type=vehicle_name or "Not specified",
        budget=f"${attrs.get('budget_max')}" if attrs.get("budget_max") else "Not specified",
        style=attrs.get("style") or "Not specified",
        resolved_product=state.get("resolved_product") or "None",
        is_relaxed=str(is_relaxed),
        stock_confirmed=str(stock_confirmed),
        product_data=formatted_products,
        customer_contact=state.get("customer_email") or state.get("has_email") or "Not on file"
    )

    # 4. LLM INVOCATION
    synth_history = full_history[-4:] if len(full_history) > 4 else full_history
    
    llm = get_llm()
    full_content = ""
    async for chunk in llm.astream([
        {"role": "system", "content": full_system_prompt},
        *synth_history
    ]):
        full_content += chunk.content

    # 5. POST-GENERATION ENFORCEMENT
    logger.info(f"Synthesizer: Strategy='{cta_intent}' Products={len(products)} LLM_Length={len(full_content)}")

    # Strip filler
    filler_patterns = [r"just a moment", r"let me check", r"searching inventory", r"one second"]
    for pattern in filler_patterns:
        full_content = re.sub(pattern, "", full_content, flags=re.IGNORECASE).strip()

    # --- GLOBAL STRATEGY FIREWALL ---
    # If we are NOT in the closing stage, but the LLM hallucinated lead-capture text:
    if sales_stage != "closing":
        # Hard-nuke any email/quote talk or "Excellent choice" if we aren't supposed to be closing
        hallucination_pattern = r"(?i).*(excellent choice|stock is confirmed|what's your name|email address|send you the quote|official quote|excellent selection)[\.\!\?]?.*"
        if re.search(hallucination_pattern, full_content):
            logger.warning(f"Synthesizer: Hallucination detected in stage '{sales_stage}'. Nuking LLM text.")
            if cta_intent == "show_options":
                full_content = f"I've verified the fitment for your {vehicle_name}. Here are some premium options for your build:"
            elif cta_intent == "ask_vehicle":
                full_content = f"I've got a great selection of wheels for your {vehicle_name}. To be 100% sure on fitment, is that the exact model you're outfitting?"
            else:
                full_content = "I'm ready to find your perfect wheels. What specifically are you looking for in terms of style or performance?"

    lines = full_content.strip().split("\n")
    text_lines = [l for l in lines if not l.strip().startswith("-")]
    product_lines = [l for l in lines if l.strip().startswith("-")]
    
    # Mandatory Product Recovery
    if cta_intent == "show_options" and products and not product_lines:
        logger.info("Synthesizer: Manually injecting product list.")
        product_lines = formatted_products.split("\n")
    
    # Final safety: Ensure we have some text
    if not text_lines:
        if cta_intent == "show_options":
            text_lines = [f"I've identified these premium options for your {vehicle_name}:"]
        elif cta_intent == "product_detail":
            text_lines = [f"I'm pulling the latest technical specifications for those wheels now. What specifically can I clarify for you?"]
        elif cta_intent == "ask_lead_info":
            text_lines = ["Excellent choice. What's your name and email so I can send the official quote?"]
        else:
            if vehicle_name != "Not specified":
                text_lines = [f"I'm here to ensure your {vehicle_name} build is perfect. Did you have any specific questions about these wheels, or should we explore other fitment options?"]
            else:
                text_lines = ["I'm ready to find the perfect wheel fitment for your build. To get started, what kind of vehicle are we outfitting today?"]

    if len(text_lines) > 3: text_lines = text_lines[:3]
    
    final_output = "\n".join(text_lines).strip()
    if product_lines:
        final_output += "\n\n" + "\n".join(product_lines)

    return {
        "messages": [AIMessage(content=final_output)],
        "last_action": action_type,
        "final_response": final_output
    }
