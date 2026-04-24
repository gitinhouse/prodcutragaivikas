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
    if not (make and model and year):
        logger.info(f"Recommender: Partial vehicle info. Showing featured options while asking for vehicle.")
        
        # Pull some generic high-stock wheels to keep the user engaged
        featured_wheels = await ProductService.universal_search(
            query_text="popular wheels",
            entities=entities,
            limit=3
        )
        
        return {
            "raw_response_data": {
                "action": "discovery", 
                "cta_intent": "ask_vehicle", 
                "total_results": len(featured_wheels), 
                "shown_results": len(featured_wheels),
                "products": featured_wheels
            },
            "cta_intent": "ask_vehicle",
            "has_valid_results": len(featured_wheels) > 0
        }

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
                    "cta_intent": "no_results",
                    "original_product": resolved_product
                },
                "sales_stage": "recommend",
                "has_valid_results": False
            }

    # 2. LAYER 1: Candidate Generation
    brand_filter = entities.get("wheel_brand")
    results = await ProductService.get_wheels_by_fitment(
        make=make, model=model, year=year,
        entities=entities, limit=12
    )
    
    # 2.5 BRAND FILTER (If user specified a brand)
    if brand_filter:
        brand_results = [p for p in results if brand_filter.lower() in p.get("brand_name", "").lower()]
        if brand_results:
            results = brand_results
            logger.info(f"Recommender: Filtered by brand '{brand_filter}' - {len(results)} matches.")

    # 3. LAYER 2: Fitment Guard (Diameter/Width & Bolt Pattern)
    guarded_results = [
        p for p in results 
        if FitmentGuard.validate(vehicle_context, p) and 
           FitmentGuard.validate_pattern(make, p.get("bolt_pattern", ""))
    ]
    
    # 4. LAYER 3: Smart Relaxation & Filtering
    requested_size = entities.get("size")
    is_more_request = (state.get("intent") == "show_more_options") or ("more" in state.get("last_user_query", "").lower())
    
    # CRITICAL: Only filter out shown products if the user is explicitly asking for 'more' or 'others'.
    # If they provide a specific filter (size/brand), show them everything that matches that filter.
    if is_more_request:
        available_results = [p for p in guarded_results if p.get("marketing_name") not in shown_products]
    else:
        available_results = guarded_results
        
    final_results = available_results
    is_relaxed = False
    
    if requested_size and available_results:
        size_match = re.search(r"(\d{2})", str(requested_size))
        if size_match:
            target_diameter = float(size_match.group(1))
            size_filtered = [p for p in available_results if float(re.search(r"(\d{2})x", p.get("marketing_name", "")).group(1)) == target_diameter]
            if size_filtered:
                final_results = size_filtered
            else:
                is_relaxed = True # No matches for that size, keeping all available options
    
    # 5. FAILURE GUARD (Context Aware)
    if not final_results:
        # If we ALREADY have products shown for this vehicle, don't say the vehicle is unsupported!
        if shown_products:
            logger.warning("Recommender: No new results found, but vehicle is already validated. Falling back.")
            return {
                "raw_response_data": {
                    "action": "recommend",
                    "cta_intent": "show_options",
                    "products": [{"marketing_name": p, "ai_reason": "Previously shown option"} for p in shown_products[:3]],
                    "total_results": len(shown_products),
                    "shown_results": min(3, len(shown_products))
                },
                "has_valid_results": True
            }
        
        # Only pivot if this is truly the first attempt and we found nothing
        logger.warning(f"Recommender: ZERO results found for {make} {model}. Forcing no_results strategy.")
        return {
            "raw_response_data": {
                "action": "no_fitment_found",
                "cta_intent": "no_results",
                "total_results": 0,
                "shown_results": 0
            },
            "cta_intent": "no_results",
            "has_valid_results": False
        }

    # 6. PRODUCT ENRICHMENT
    reasons = ["aggressive stance", "rugged daily", "premium street look", "clean finish"]
    trimmed_products = []
    for i, p in enumerate(final_results[:4]):
        trimmed_products.append({
            "marketing_name": p.get("marketing_name"),
            "price": p.get("price"),
            "stock": p.get("stock", 0),
            "finish": p.get("finish") or "Premium",
            "bolt_pattern": p.get("bolt_pattern") or "Verified",
            "ai_reason": reasons[i % 4] if not is_relaxed else f"Compatible {make} fitment"
        })

    new_shown = [p.get("marketing_name") for p in final_results[:4]]
    is_new_search = (state.get("intent") in ["product_search", "show_more_options"])
    total_found = len(guarded_results)

    return {
        "raw_response_data": {
            "action": "recommend",
            "cta_intent": cta_intent,
            "products": trimmed_products,
            "total_results": total_found,
            "shown_results": len(trimmed_products),
            "is_relaxed_search": is_relaxed,
            "is_new_recommendation": is_new_search, # Help synthesizer distinguish
            "allow_lead_capture": (sales_stage == "closing" or cta_intent == "offer_quote")
        },
        "recommended_products": new_shown,
        "shown_products": list(set(shown_products + new_shown)),
        "has_valid_results": True
    }
