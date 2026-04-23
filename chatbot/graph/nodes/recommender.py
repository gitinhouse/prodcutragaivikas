import logging
import re
from chatbot.graph.state import GraphState
from chatbot.services.product_service import ProductService
from chatbot.helpers.fitment_guard import FitmentGuard

# 🔥 MASTER LOGGER FOR TRACEABILITY
logger = logging.getLogger("chatbot.nodes.recommender")

async def recommender_node(state: GraphState):
    """
    Expert Recommendation Node V8.
    Implements Live Inventory Verification for the Closing Stage.
    """
    entities = state.get("extracted_entities", {})
    vehicle_context = state.get("vehicle_context", {})
    cta_intent = state.get("cta_intent", "show_options")
    sales_stage = state.get("sales_stage", "recommendation")
    shown_products = state.get("shown_products", [])
    resolved_product = state.get("resolved_product")
    
    make = vehicle_context.get("make")
    model = vehicle_context.get("model")
    year = vehicle_context.get("year")
    
    # 1. SOFT GUARD: Missing Vehicle
    if not (make and model):
        return {"raw_response_data": {"action": "discovery"}, "has_valid_results": False}

    # --- STAGE 0: LIVE INVENTORY CHECK (Closing Phase) ---
    # CRITICAL: Only enter closing if the CURRENT Controller explicitly said ask_lead_info.
    # Checking sales_stage alone reads stale checkpointer state from prior sessions.
    if sales_stage == "closing" and cta_intent == "ask_lead_info" and resolved_product:
        logger.info(f"Recommender: Performing LIVE inventory check for {resolved_product}")
        stock_status = await ProductService.check_inventory_status(resolved_product)
        
        if stock_status.get("is_available"):
            logger.info("Recommender: Stock confirmed.")
            return {
                "raw_response_data": {
                    "action": "recommend",
                    "cta_intent": "ask_lead_info",
                    "products": [stock_status["product"]],
                    "stock_confirmed": True,
                    "allow_lead_capture": True
                },
                "has_valid_results": True
            }
        else:
            logger.warning("Recommender: Selection is OUT OF STOCK. Pivoting.")
            # Move back to recommendation stage to suggest something else
            return {
                "raw_response_data": {
                    "action": "out_of_stock",
                    "cta_intent": "technical_pivot",
                    "original_product": resolved_product
                },
                "sales_stage": "recommend",
                "has_valid_results": False
            }

    # 2. LAYER 1: Candidate Generation
    results = await ProductService.get_wheels_by_fitment(
        make=make, model=model, year=year,
        entities=entities, limit=12
    )
    
    # 3. LAYER 2: Fitment Guard
    guarded_results = [p for p in results if FitmentGuard.validate(vehicle_context, p)]
    
    # 4. LAYER 3: Smart Relaxation
    requested_size = entities.get("size")
    final_results = guarded_results
    is_relaxed = False
    
    if requested_size:
        size_match = re.search(r"(\d{2})", str(requested_size))
        if size_match:
            target_diameter = float(size_match.group(1))
            final_results = [p for p in guarded_results if float(re.search(r"(\d{2})x", p.get("marketing_name", "")).group(1)) == target_diameter and p.get("marketing_name") not in shown_products]
            if not final_results:
                final_results = [p for p in guarded_results if p.get("marketing_name") not in shown_products]
                is_relaxed = True
    
    # 5. FAILURE GUARD
    if not final_results:
        return {"raw_response_data": {"action": "no_fitment_found"}, "has_valid_results": False}

    # 6. PRODUCT ENRICHMENT
    reasons = ["aggressive stance", "rugged daily", "premium street look", "clean finish"]
    trimmed_products = []
    for i, p in enumerate(final_results[:4]):
        trimmed_products.append({
            "marketing_name": p.get("marketing_name"),
            "price": p.get("price"),
            "stock": p.get("stock", 0),
            "ai_reason": reasons[i % 4] if not is_relaxed else f"Compatible {make} fitment"
        })

    new_shown = [p.get("marketing_name") for p in final_results[:4]]
    return {
        "raw_response_data": {
            "action": "recommend",
            "cta_intent": cta_intent,
            "products": trimmed_products,
            "is_relaxed_search": is_relaxed,
            "allow_lead_capture": (sales_stage == "closing" or cta_intent == "offer_quote")
        },
        "recommended_products": new_shown,
        "shown_products": shown_products + new_shown,
        "has_valid_results": True
    }
