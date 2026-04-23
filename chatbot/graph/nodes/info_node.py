import logging
import re
from chatbot.graph.state import GraphState
from chatbot.services.product_service import ProductService

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.info")

async def info_node(state: GraphState):
    """
    Expert Technical Info Node.
    Hardened for context-aware resolution and sales-aligned gating.
    """
    query_text = state.get("last_user_query", "").lower()
    entities = state.get("extracted_entities", {})
    cta_intent = state.get("cta_intent", "show_options")
    sales_stage = state.get("sales_stage", "recommendation")
    
    logger.info(f"Info Node: Resolving technical context for '{query_text}'")

    # 1. ATTEMPT UNIVERSAL MATCH (SKU/NAME FOCUS)
    results = await ProductService.universal_search(
        query_text=query_text,
        entities=entities,
        limit=2
    )
    
    # 2. SMART CONTEXT RESOLUTION (Pronoun/Direct Reference)
    current_resolved_name = state.get("resolved_product")
    new_resolved = results[0] if results else None
    
    # If no new result but we have a current one in state, try to re-resolve it
    if not new_resolved and current_resolved_name:
        # Re-fetch from DB to get fresh specs
        context_results = await ProductService.universal_search(
            query_text=current_resolved_name,
            entities=entities,
            limit=1
        )
        if context_results:
            new_resolved = context_results[0]

    final_product_data = None
    if new_resolved:
        # Construct Enriched Technical Structure
        specs = new_resolved.get("specification", {})
        final_product_data = {
            "name": new_resolved.get("name"),
            "brand": new_resolved.get("brand_name"),
            "stock": new_resolved.get("stock", 0),
            "bolt_pattern": new_resolved.get("bolt_pattern") or "Verified Fitment",
            "size": f"{new_resolved.get('diameter', 'N/A')}\" x {new_resolved.get('width', 'N/A')}\"",
            "finish": new_resolved.get("finish") or "Premium Finish",
            "price": new_resolved.get("price"),
            "details": new_resolved.get("ai_summary", "High-performance technical specifications."),
            "raw_specs": specs
        }

    # 3. SMART LIST FILTERING (For "Which one is black?" type questions)
    if re.search(r"(which|any|these|show|have|ones|all)", query_text):
        color_match = re.search(r"(black|silver|matte|gloss|chrome|gold|bronze)", query_text)
        if color_match:
            color = color_match.group(1)
            logger.info(f"Info Node: Filtering shown products for color '{color}'")
            # We already have results from universal_search, let's use them
            matching_names = [r.get("marketing_name") for r in results if color in r.get("finish", "").lower() or color in r.get("ai_summary", "").lower()]
            if matching_names:
                final_product_data = {
                    "name": "Selection Results",
                    "details": f"The following models are available in {color}: " + ", ".join(matching_names)
                }
            else:
                final_product_data = {
                    "name": "Selection Results",
                    "details": f"I'm checking the specific finishes for those models. While {color} is a popular choice, let's look at the exact options for your build."
                }

    # 3. STRATEGIC GATING
    allow_lead = (sales_stage == "closing" or cta_intent == "offer_quote")

    return {
        "raw_response_data": {
            "action": "info",
            "cta_intent": cta_intent,
            "product_info": final_product_data or {"name": "General Inquiries", "details": "Expert advice requested."},
            "allow_lead_capture": allow_lead
        },
        "resolved_product": final_product_data.get("name") if final_product_data else None
    }
