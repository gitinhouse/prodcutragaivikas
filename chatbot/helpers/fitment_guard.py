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

    # Bolt Pattern Knowledge Base (The 'Fitment Bible')
    MAKE_PATTERNS = {
        "ford": ["6x135", "5x108", "5x114.3"], # F-150 is 6x135, Mustang is 5x114.3
        "toyota": ["6x139.7", "5x114.3", "5x150"], # Tacoma 6-lug, Camry 5-lug, Tundra 5-lug
        "bmw": ["5x120", "5x112"],
        "audi": ["5x112"],
        "mercedes": ["5x112"],
        "honda": ["5x114.3", "5x120"],
        "tesla": ["5x114.3", "5x120"],
        "jeep": ["5x127", "5x114.3"]
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

    @staticmethod
    def validate_pattern(vehicle_make, product_pattern):
        """
        Technical verification of bolt pattern against make-specific standards.
        """
        if not vehicle_make or not product_pattern:
            return True # Insufficient data to reject
            
        make_low = vehicle_make.lower().strip()
        pattern_low = product_pattern.lower().replace(" ", "")
        
        # Resolve patterns for the make
        valid_patterns = FitmentGuard.MAKE_PATTERNS.get(make_low)
        if not valid_patterns:
            return True # Make unknown to guard
            
        # Check for direct match or partial match (e.g. '5x112' in '5x112 / 5x120')
        if any(p.lower() in pattern_low for p in valid_patterns):
            return True
            
        logger.warning(f"FitmentGuard: BOLT PATTERN REJECTED. {product_pattern} is technically impossible for {vehicle_make}.")
        return False

import re # Needed for the static method
