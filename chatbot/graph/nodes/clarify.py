import logging
from chatbot.graph.state import GraphState
from chatbot.helpers.prompts import DISCOVERY_PROMPT, STATIC_MESSAGES
from chatbot.services.product_service import ProductService

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.clarify")

async def clarify_node(state: GraphState):
    """
    Expert Discovery Node.
    Hardened for 'Value-First' Retrieval: Shows products even during discovery.
    """
    is_greeting = state.get("is_greeting", False)
    entities = state.get("extracted_entities", {})
    query_text = state.get("last_user_query", "")
    
    logger.info(f"Clarify: Initiating Value-First Discovery (Greeting={is_greeting})...")

    # 1. FETCH BROAD FEATURED PRODUCTS (Instant Gratification)
    # We run a broad universal search using whatever context we have (e.g. SUV, Truck)
    # This ensures the user sees wheels immediately.
    logger.info(f"Clarify: Fetching category-featured items for immediate value...")
    broad_results = await ProductService.universal_search(
        query_text=query_text if not is_greeting else "featured wheels",
        entities=entities,
        limit=3
    )
    
    # 2. FETCH CATALOG OVERVIEW (Brands)
    catalog = await ProductService.get_catalog_overview()
    available_brands = catalog.get("brands", [])[:8]
    
    # 3. CONSTRUCT PAYLOAD
    if is_greeting:
        logger.info("Clarify: Setting action to 'greeting' for natural persona response.")
        return {
            "raw_response_data": {
                "action": "greeting",
                "brands": available_brands,
                "products": broad_results,
                "message": STATIC_MESSAGES["greeting"]
            }
        }

    # NORMAL DISCOVERY TRACK with 'Value-First' products
    logger.info(f"Clarify: Setting action to 'discovery' with {len(broad_results)} featured products.")
    return {
        "raw_response_data": {
            "action": "discovery",
            "brands": available_brands,
            "products": broad_results,
            "instruction": DISCOVERY_PROMPT
        }
    }
