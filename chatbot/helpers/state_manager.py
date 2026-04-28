import logging
import re
from chatbot.helpers.config_cache import ConfigCache

logger = logging.getLogger("chatbot.helpers.state_manager")

class StateManager:
    """
    THE DETERMINISTIC DECISION ENGINE V7.
    Derives Phase from State and manages Surgical Memory Resets.
    """

    PHASES = {
        "VEHICLE_COLLECTION": "discovery",
        "READY_FOR_SEARCH": "fitment",
        "BROWSING": "recommendation",
        "PURCHASE": "closing"
    }

    CORE_FIELDS = ["vehicle_context", "budget_max", "wheel_brand"]
    SESSION_FIELDS = ["shown_products", "resolved_product", "active_filters", "view_count", "loop_count"]
    
    @staticmethod
    def resolve_phase(state):
        """
        DERIVED PHASE RESOLVER: The source of truth for conversation progress.
        """
        vc = state.get("vehicle_context", {})
        vehicle_complete = bool(vc.get("year") and vc.get("make") and vc.get("model"))
        results_shown = len(state.get("shown_products", [])) > 0
        checkout_started = state.get("cta_intent") in ["ask_lead_info", "confirm_order_on_file", "close"]
        email_captured = bool(state.get("customer_email") or state.get("has_email"))

        if not vehicle_complete:
            return "VEHICLE_COLLECTION"
        if not results_shown:
            return "READY_FOR_SEARCH"
        if not (checkout_started or email_captured):
            return "BROWSING"
        return "PURCHASE"

    @staticmethod
    async def process_state(state, new_entities, query):
        """
        Main entry point for state updates.
        """
        # 0. VALIDATE INGRESS
        if state is None: return {}
        
        attrs = new_entities.get("attributes", {})
        intent = new_entities.get("intent", "product_search")
        
        # 1. DETECT CORRECTIONS (Confidence Layer)
        is_correction = await StateManager._is_confirmed_correction(state, attrs, intent)
        
        # 2. APPLY MEMORY TIERS & SURGICAL RESETS
        updates = {}
        if is_correction or new_entities.get("signal_type") == "RESET":
            # For Nuclear Pivots (RESET), we pass empty attrs to force a clean slate
            updates = await StateManager._handle_surgical_reset(state, attrs)
        else:
            updates = await StateManager._handle_standard_update(state, attrs)

        # 3. FILTER PERSISTENCE & CONFLICT RESOLUTION
        current_filters = state.get("active_filters", {})
        
        # Reset Logic: If 'all' or 'any' was detected, clear the sticky filters
        if new_entities.get("reset_filters"):
            logger.info("StateManager: Clearing persistent filters for broad search.")
            current_filters = {}

        new_filters = {
            "size": attrs.get("size"),
            "finish": attrs.get("finish"),
            "style": attrs.get("style") or attrs.get("usage")
        }
        # Merge logic: New overrides old if present
        merged_filters = {k: v for k, v in current_filters.items()}
        for k, v in new_filters.items():
            if v: merged_filters[k] = v
        
        updates["active_filters"] = merged_filters

        # 4. DERIVE PHASE & PROGRESS
        temp_state = {**state, **updates}
        updates["phase"] = StateManager.resolve_phase(temp_state)
        updates["sales_stage"] = StateManager.PHASES.get(updates["phase"], "discovery")

        # 5. LOOP & VIEW TRACKING
        if intent == "show_more_options" or "more" in query.lower():
            updates["loop_count"] = state.get("loop_count", 0) + 1
        
        return updates

    @staticmethod
    async def _is_confirmed_correction(state, attrs, intent):
        """
        Confidence + Pattern detection for corrections.
        """
        new_make = attrs.get("vehicle_make")
        old_make = state.get("vehicle_context", {}).get("make")
        
        if not new_make or not old_make: return False
        if new_make.lower() == old_make.lower(): return False
        
        # Check if it's a known car make (Security Guard)
        is_valid_car = await ConfigCache.is_known_make(new_make)
        if not is_valid_car: return False
        
        # Check if it's actually a wheel brand (Security Guard)
        wheel_brands = await ConfigCache.get_wheel_brands()
        if new_make.lower() in [b.lower() for b in wheel_brands]: return False
        
        return True

    @staticmethod
    async def _handle_surgical_reset(state, attrs):
        """
        Resets SESSION memory but protects CORE context.
        """
        logger.info("StateManager: Surgical Reset Triggered (Vehicle Correction).")
        vc = {} # Clear vehicle for correction
        for key, attr_key in {"year": "vehicle_year", "make": "vehicle_make", "model": "vehicle_model"}.items():
            if attrs.get(attr_key): vc[key] = attrs[attr_key]
            
        return {
            "vehicle_context": vc,
            "vehicle_locked": bool(vc.get("year") and vc.get("make") and vc.get("model")),
            "shown_products": [],
            "resolved_product": None,
            "view_count": 0,
            "loop_count": 0,
            "active_filters": {k: v for k, v in state.get("active_filters", {}).items() if k in ["style", "finish"]}
        }

    @staticmethod
    async def _handle_standard_update(state, attrs):
        """
        Sticky Context: Merges new attributes without losing old ones.
        """
        vc = (state.get("vehicle_context") or {}).copy()
        
        # Merge logic: Only overwrite if the new value is NOT None/empty
        if attrs.get("vehicle_year"): vc["year"] = attrs["vehicle_year"]
        if attrs.get("vehicle_make"): vc["make"] = attrs["vehicle_make"]
        if attrs.get("vehicle_model"): vc["model"] = attrs["vehicle_model"]
            
        return {
            "vehicle_context": vc,
            "vehicle_locked": bool(vc.get("year") and vc.get("make") and vc.get("model")),
            "budget_max": attrs.get("budget_max") or state.get("budget_max")
        }
