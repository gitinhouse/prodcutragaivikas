import logging
from chatbot.graph.state import GraphState
from chatbot.helpers.prompts import INFO_PROMPT
from chatbot.services.product_service import ProductService

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.info")

async def info_node(state: GraphState):
    """
    Expert Technical Info Node.
    Hardened to use Universal Search for high-precision product resolution.
    """
    query_text = state.get("last_user_query", "")
    entities = state.get("extracted_entities", {})
    
    logger.info(f"Info Node: Resolving technical context for '{query_text}'")

    # 1. ATTEMPT UNIVERSAL MATCH (SKU/NAME FOCUS)
    results = await ProductService.universal_search(
        query_text=query_text,
        entities=entities,
        limit=2
    )
    
    # MEMORY FALLBACK: If no results for 'buy it' or pronouns, keep current product
    current_resolved = state.get("resolved_product")
    new_resolved = results[0] if results else None
    
    # Pronoun detection: If query is very short and we had a product, don't clear it!
    pronouns = ["it", "this", "that", "those", "buy", "price", "more"]
    is_pronoun_query = any(p in query_text.lower().split() for p in pronouns) or len(query_text.split()) < 3
    
    if not new_resolved and current_resolved and is_pronoun_query:
        logger.info(f"Info Node: Maintaining context for '{current_resolved}' due to pronoun/short query.")
        resolved_product_name = current_resolved
    else:
        resolved_product_name = new_resolved["marketing_name"] if new_resolved else None
    
    if resolved_product_name:
        logger.info(f"Info Node: Technical context resolved/maintained as '{resolved_product_name}'")
    else:
        logger.info("Info Node: No specific product resolved. Providing general technical guidance.")

    # 2. CONSTRUCT PAYLOAD
    main_product = new_resolved if new_resolved else {"marketing_name": resolved_product_name}
    similar_products = results[1:] if len(results) > 1 else []
    
    return {
        "resolved_product": resolved_product_name,
        "raw_response_data": {
            "action": "info",
            "product": main_product,
            "similar_products": similar_products,
            "instruction": INFO_PROMPT,
            "allow_lead_capture": True
        }
    }
