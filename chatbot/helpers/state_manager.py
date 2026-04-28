import logging
import re
from chatbot.helpers.validator import validate_state, debug_log

logger = logging.getLogger("chatbot.helpers.state_manager")

class StateManager:
    """
    THE STATE AUTHORITY V6: Logical Progression Engine.
    Ensures the user MUST see products before entering the closing stage.
    """

    STYLE_MAP = {
        "daily use": "balanced",
        "sporty": "performance",
        "rugged": "offroad",
        "luxury": "luxury"
    }

    CATEGORY_MAP = {
        "rim": "wheels",
        "rims": "wheels",
        "wheel": "wheels",
        "wheels": "wheels",
        "tire": "tires",
        "tyre": "tires"
    }

    @staticmethod
    def process_state(current_state, new_entities, query):
        # 1. CATEGORY NORMALIZATION
        new_intent = new_entities.get("intent", current_state.get("intent"))
        raw_cat = new_entities.get("category", "wheels")
        if "wheel" in query.lower() or "rim" in query.lower():
            raw_cat = "wheels"
        
        # 2. DELTA CONSTRUCTION
        updates = {
            "category": StateManager.CATEGORY_MAP.get(raw_cat.lower(), "wheels")
        }
        
        # 3. MERGE & RESOLVE
        merge_updates = StateManager.merge_and_resolve(current_state, new_entities)
        updates.update(merge_updates)
        
        # 4. CONTEXTUAL FOLLOW-UP
        updates["is_follow_up"] = StateManager.detect_follow_up({**current_state, **updates}, query)
        
        # 5. STAGE CALCULATION
        updates["sales_stage"] = StateManager.calculate_stage({**current_state, **updates}, new_intent)
        
        # 6. ENFORCE BUSINESS TRUTH (Return only the changes)
        return updates

    @staticmethod
    def merge_and_resolve(state, new_entities):
        updates = {}
        vc = state.get("vehicle_context", {}).copy()
        entities = state.get("extracted_entities", {}).copy()
        attrs = new_entities.get("attributes", {})
        
        new_make = attrs.get("vehicle_make")
        new_model = attrs.get("vehicle_model")
        old_make = vc.get("make")
        
        # WHEEL BRAND SHIELD: Don't reset if "new_make" is actually a wheel brand
        WHEEL_BRANDS = ["bbs", "vossen", "fuel", "rohana", "tsw", "dirty life", "method", "american"]
        is_wheel_brand = new_make and new_make.lower() in WHEEL_BRANDS

        # VEHICLE BRAND VALIDATION: Only reset if the new_make is a KNOWN automotive brand
        KNOWN_CARS = ["honda", "bmw", "audi", "mercedes", "ford", "chevy", "chevrolet", "toyota", "nissan", "jeep", "dodge", "ram", "subaru", "lexus", "hyundai", "kia", "volkswagen", "porsche", "tesla", "gmc", "cadillac", "mazda", "maruti", "suzuki", "tata", "mahindra", "hyundai", "kia"]
        is_valid_car = new_make and new_make.lower() in KNOWN_CARS
        
        # RESET IF MAKE CHANGES (Even without model) - Guarded by Wheel Shield and Car Validation
        if new_make and old_make and new_make.lower() != old_make.lower() and not is_wheel_brand and is_valid_car:
            logger.info(f"StateManager: Make changed from {old_make} to {new_make}. Resetting context.")
            updates["extracted_entities"] = {}
            updates["shown_products"] = []
            updates["wheel_size"] = None
            updates["resolved_product"] = None
            updates["sales_stage"] = "discovery"
            vc = {}
            entities = {}
        
        # RESET IF FULL NEW CAR PROVIDED (Guarded by Wheel Brand Shield)
        elif new_make and new_model and not is_wheel_brand:
            old_car = f"{vc.get('make','')}{vc.get('model','')}".lower()
            new_car = f"{new_make}{new_model}".lower()
            if old_car and old_car != new_car:
                logger.info("StateManager: Vehicle change detected. Triggering Nuclear Reset.")
                updates["extracted_entities"] = {}
                updates["shown_products"] = []
                updates["wheel_size"] = None
                updates["resolved_product"] = None
                updates["sales_stage"] = "discovery"
                vc = {}
                entities = {}

        for key, attr_key in {"year": "vehicle_year", "make": "vehicle_make", "model": "vehicle_model"}.items():
            if attrs.get(attr_key):
                vc[key] = attrs[attr_key]
        
        updates["vehicle_context"] = vc
        # MANDATORY VALIDATION: Locked only if we have Year, Make, and Model to ensure fitment precision
        updates["vehicle_locked"] = bool(vc.get("year") and vc.get("make") and vc.get("model"))

        if attrs.get("size"):
            updates["wheel_size"] = attrs["size"]
            
        if attrs.get("wheel_brand"):
            updates["wheel_brand"] = attrs["wheel_brand"]
            
        if attrs.get("budget_max"):
            updates["budget_max"] = attrs["budget_max"]
            
        entities.update({
            "size": updates.get("wheel_size", state.get("wheel_size")),
            "wheel_brand": updates.get("wheel_brand", state.get("wheel_brand")),
            "budget_max": updates.get("budget_max", state.get("budget_max")),
            "vehicle_make": vc.get("make"),
            "vehicle_model": vc.get("model")
        })
        updates["extracted_entities"] = entities
        return updates

    @staticmethod
    def detect_follow_up(state, query):
        words = query.lower().split()
        confirmation_words = ["ok", "sure", "yes", "yeah", "yep", "good", "great"]
        is_confirm = any(w in words for w in confirmation_words) and len(words) <= 3
        has_context = state.get("vehicle_locked") or state.get("wheel_size")
        return is_confirm and has_context

    @staticmethod
    def calculate_stage(state, current_intent):
        """
        STRICT PROGRESSION: Discovery -> Recommendation -> Closing.
        """
        has_vehicle = state.get("vehicle_locked")
        has_pref = bool(state.get("wheel_size"))
        resolved_product = state.get("resolved_product")
        
        # --- INVARIANTS & RESET RULES ---
        shown_products = state.get("shown_products", [])

        # 1. NO PRODUCTS = NO CLOSING
        if not shown_products and (state.get("sales_stage") == "closing" or current_intent == "purchase_intent"):
            logger.warning("StateManager: Closing stage blocked - no products shown yet.")
            return "recommend" if has_vehicle else "discovery"

        # 2. INTENT OVERRIDE: If they want to search/browse
        if current_intent in ["product_search", "show_more_options", "greeting", "fitment_lookup", "recommendation", "fitment_check"]:
            # If they explicitly want more/different options, clear the 'resolved' purchase target
            if current_intent == "show_more_options":
                state["resolved_product"] = None
                
            # ONLY RESET IF VEHICLE IS NEW OR MISSING
            if not state.get("vehicle_locked"):
                logger.info("StateManager: New/Unconfirmed vehicle context. Resetting results.")
                state["resolved_product"] = None
                state["shown_products"] = []
            
            if has_vehicle and has_pref: return "recommend"
            elif has_vehicle: return "guided_discovery"
            return "discovery"

        # 3. NO VEHICLE = NO RECOMMENDATION/CLOSING
        if not has_vehicle:
            # Force reset if vehicle context was cleared or is incomplete
            state["resolved_product"] = None
            state["shown_products"] = []
            return "discovery"

        # --- RULE: CLOSING REQUIRES A PRODUCT ---
        if current_intent == "purchase_intent" or state.get("sales_stage") == "closing":
            if resolved_product and resolved_product != "None":
                return "closing"
            # Fall back to recommendation if they try to buy nothing
            return "recommend" if has_vehicle else "discovery"
            
        if has_vehicle and has_pref: return "recommend"
        elif has_vehicle: return "guided_discovery"
        return "discovery"
