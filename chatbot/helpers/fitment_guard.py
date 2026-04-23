import logging

logger = logging.getLogger("chatbot.helpers.fitment_guard")

class FitmentGuard:
    """
    DETERMINISTIC FITMENT SAFETY: The 'Sanity Check' Layer.
    Prevents the LLM/DB from recommending physically impossible wheels.
    Example: 22" wheels on an Audi A4.
    """
    
    # Class-based constraints (Physical Limits)
    LIMITS = {
        "sedan": {"max_diameter": 20, "max_width": 9.5},
        "coupe": {"max_diameter": 20, "max_width": 9.5},
        "hatchback": {"max_diameter": 19, "max_width": 8.5},
        "suv": {"max_diameter": 26, "max_width": 12.0},
        "truck": {"max_diameter": 28, "max_width": 14.0},
        "jeep": {"max_diameter": 24, "max_width": 12.0}
    }

    @staticmethod
    def validate(vehicle_context, product):
        """
        Returns True if product is within sane physical limits for the vehicle type.
        """
        v_type = str(vehicle_context.get("type", "sedan")).lower()
        make = str(vehicle_context.get("make", "")).lower()
        model = str(vehicle_context.get("model", "")).lower()
        
        # 1. HEURISTIC OVERRIDE: If type is missing, infer from common sedans
        sedan_brands = ["audi", "bmw", "mercedes", "honda", "toyota", "lexus", "tesla"]
        if not v_type or v_type == "none":
            if any(b in make for b in sedan_brands):
                v_type = "sedan"
            if any(m in model for m in ["civic", "accord", "a4", "a3", "3 series", "c class", "corolla"]):
                v_type = "sedan"

        # 2. RESOLVE LIMITS
        limits = FitmentGuard.LIMITS.get(v_type, FitmentGuard.LIMITS["sedan"])
        
        # 3. EXTRACT PRODUCT DIMENSIONS
        # We look for diameter/width in the product attributes or name
        # Name example: "Bbs Model-12 (22x10)"
        name = product.get("marketing_name", "")
        dimensions = re.search(r"(\d{2})x(\d{1,2}\.?\d?)", name)
        
        if dimensions:
            diameter = float(dimensions.group(1))
            width = float(dimensions.group(2))
            
            # 4. ENFORCE LIMITS
            if diameter > limits["max_diameter"]:
                logger.warning(f"FitmentGuard: REJECTED {name} for {v_type} (Diameter {diameter} > {limits['max_diameter']})")
                return False
            
            if width > limits["max_width"]:
                logger.warning(f"FitmentGuard: REJECTED {name} for {v_type} (Width {width} > {limits['max_width']})")
                return False

        return True

import re # Needed for the static method
