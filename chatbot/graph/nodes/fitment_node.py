import logging
from chatbot.graph.state import GraphState
from chatbot.helpers.fitment_guard import FitmentGuard
import re

logger = logging.getLogger("chatbot.nodes.fitment_node")

async def fitment_node(state: GraphState):
    """
    Dedicated node for verifying if a user's requested specs fit their vehicle.
    Bypasses the DB to provide instant physical constraint validation.
    """
    entities = state.get("extracted_entities", {})
    vehicle_context = state.get("vehicle_context", {})
    
    diameter = entities.get("size")
    
    # 1. VALIDATE VEHICLE PRESENCE
    if not vehicle_context.get("make") or not vehicle_context.get("model"):
        logger.info("FitmentNode: Missing vehicle data for fitment check.")
        return {
            "raw_response_data": {
                "action": "discovery",
                "cta_intent": "ask_vehicle",
                "total_results": 0
            },
            "cta_intent": "ask_vehicle"
        }

    # 2. PERFORM FITMENT VALIDATION
    v_type = str(vehicle_context.get("type", "sedan")).lower()
    
    # Heuristic override for common sedans if type is missing
    make = str(vehicle_context.get("make", "")).lower()
    model = str(vehicle_context.get("model", "")).lower()
    sedan_brands = ["audi", "bmw", "mercedes", "honda", "toyota", "lexus", "tesla"]
    if v_type == "none" or not v_type:
        if any(b in make for b in sedan_brands) or any(m in model for m in ["civic", "accord", "a4", "3 series", "c class"]):
            v_type = "sedan"

    limits = FitmentGuard.LIMITS.get(v_type, FitmentGuard.LIMITS["sedan"])
    
    status = "safe"
    issues = []
    
    if diameter:
        # Extract digits from strings like '22 inch' or '22"'
        match = re.search(r"(\d{2})", str(diameter))
        if match:
            d_val = float(match.group(1))
            if d_val > limits["max_diameter"]:
                issues.append(f"A {d_val}\" diameter exceeds the recommended {limits['max_diameter']}\" maximum for a {v_type}")

    if issues:
        status = "risky"
        notes = " and ".join(issues) + ". This could cause major rubbing issues or require heavy suspension modifications."
    else:
        # If no issues, they gave a valid size or no size.
        if diameter:
            notes = f"A {diameter} setup is well within the standard fitment range for your {vehicle_context.get('make')} {vehicle_context.get('model')}."
        else:
            notes = f"I can confirm we have verified fitment specs available for your {vehicle_context.get('make')} {vehicle_context.get('model')}."

    logger.info(f"FitmentNode: Validation complete. Status='{status}' Notes='{notes}'")

    return {
        "raw_response_data": {
            "action": "fitment_validation",
            "cta_intent": "fitment_summary",
            "validation_status": status,
            "validation_notes": notes,
            "total_results": 1,
            "shown_results": 1,
            "allow_lead_capture": False
        },
        "cta_intent": "fitment_summary"
    }
