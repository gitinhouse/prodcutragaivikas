import logging
import json
import datetime

logger = logging.getLogger("chatbot.helpers.validator")

def debug_log(state, step_name="STATE_TRACE"):
    trace = {
        "STEP": step_name,
        "VEHICLE": state.get("vehicle_context"),
        "LOCKED": state.get("vehicle_locked"),
        "STAGE": state.get("sales_stage"),
        "CONFIDENCE": state.get("confidence_score"),
        "INTENT": str(state.get("intent")),
        "FOLLOW_UP": state.get("is_follow_up")
    }
    print("\n" + "="*50)
    print(json.dumps(trace, indent=2))
    print("="*50 + "\n")

def sanity_check(extracted_data):
    """
    THE SANITY LAYER: Catches confident-but-wrong data.
    Returns (is_sane, downgraded_confidence).
    """
    confidence = extracted_data.get("confidence", 1.0)
    attrs = extracted_data.get("attributes", {})
    
    # 1. YEAR SANITY
    year = attrs.get("vehicle_year")
    if year:
        try:
            y_val = int(year)
            current_year = datetime.date.today().year
            if y_val < 1980 or y_val > current_year + 1:
                logger.warning(f"Sanity: Illogical year detected ({y_val}). Downgrading.")
                return False, 0.4
        except:
            return False, 0.3

    # 2. DIMENSION SANITY
    size = attrs.get("size")
    if size:
        try:
            s_val = int(size)
            if s_val < 14 or s_val > 24:
                logger.warning(f"Sanity: Extreme wheel size ({s_val}). Downgrading.")
                return False, 0.4
        except: pass

    return True, confidence

def validate_state(state):
    """
    THE JANITOR: Enforces Business Invariants.
    """
    vc = state.get("vehicle_context", {})
    
    # 1. VEHICLE PERSISTENCE
    if state.get("vehicle_locked"):
        if not vc.get("make") or not vc.get("model"):
            state["vehicle_locked"] = False

    # 2. STAGE SANITY
    # Ensure we don't 'recommend' without a vehicle.
    if state.get("sales_stage") == "recommend" and not state.get("vehicle_locked"):
        logger.warning("Validator: Recommendation stage active without vehicle. Resetting.")
        state["sales_stage"] = "discovery"

    return state
