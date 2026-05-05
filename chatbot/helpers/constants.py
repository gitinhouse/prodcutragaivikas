"""
SEBASTIAN SALES AI - DOMAIN CONSTANTS & MASTER LISTS
Single Source of Truth (DRY Restoration Standard)
RELEVANCE > HELPFULNESS (Iron Boundary Enforced)
"""

# --- 1. WHITELIST (CORE DOMAIN) ---
WHEEL_KEYWORDS = [
    "wheel", "rim", "mag", "alloy", "offset", "bolt", "lug", "bore", 
    "diameter", "width", "finish", "black", "chrome", "matte", "gloss",
    "fuel", "dirty life", "method", "american", "truxx", "at1914", "sku",
    "truck", "suv", "jeep", "wrangler", "f150", "specs", "price", "size",
    "inch", "inches", "16", "17", "18", "20", "22", "24"
]

AUTOMOTIVE_TERMS = ["wheel", "rim", "tire", "truck", "suv", "bolt", "offset", "fitment", "stance", "spacing", "inch", "inches"]

# --- 2. SAFE CONTEXTS (GREETINGS & PLEASANTRIES) ---
# Allowing standard entries into the sales funnel
SAFE_GREETINGS = [
    "hello", "hi", "hey", "greetings", "morning", "evening", "afternoon", 
    "howdy", "sup", "yo", "helloo", "thanks", "thank you", "great"
]

STATIC_GREETINGS = [
    "Welcome to the Studio. I'm Axle — your Lead Advisor. To get us started: are you outfitting a Truck, SUV, or Jeep?",
    "Hello. Axle here. Looking to upgrade your vehicle's stance with some premium wheels? What are you driving?",
    "Welcome. I'm Axle. Let's get your build dialed in. Are we working on a Truck, SUV, or Jeep today?"
]

# --- 3. BLACKLISTS (RESTRICED CATEGORIES) ---

BANNED_OUT_OF_CATALOG = [
    "cake", "pen", "food", "shoe", "bread", "insurance", "oil", "bakery",
    "butterscotch", "medical", "doctor", "lawyer", "finance", "politics"
]

BANNED_UNSUPPORTED_AUTOMOTIVE = [
    "tire", "tyre", "lift kit", "suspension", "brake", "transmission", 
    "engine", "shocks", "shock absorber", "exhaust", "battery", "service",
    "repair", "alignment"
]

# Used by the Nuclear Response Gate for a deterministic refusal
DENIAL_MASTER_LIST = BANNED_OUT_OF_CATALOG + BANNED_UNSUPPORTED_AUTOMOTIVE

# For State Observability
VIOLATION_MAP = {
    "out_of_catalog": BANNED_OUT_OF_CATALOG,
    "unsupported_automotive": BANNED_UNSUPPORTED_AUTOMOTIVE
}

# --- 4. DOMAIN TYPES (Standardized) ---
class DomainTypes:
    IN_SCOPE = "in_scope"
    SOFT_OUT = "soft_out"
    HARD_OUT = "hard_out"

# --- 5. STATIC MESSAGES (Hard-Block & Pivot Bypasses) ---
STATIC_MESSAGES = {
    "hard_block": "I’m an expert when it comes to wheels, but that topic is a bit outside my lane! I’d love to help you perfect your build—what are we looking for in terms of setup?",
    "pivot_tires": "I focus exclusively on high-end wheel fitment, so I don't handle tires directly. However, if you're looking to upgrade your rims while you're at it, I can find you the perfect set. What are you driving?",
    "pivot_lift": "I’ll leave the lift kits to the suspension experts, but if you want wheels that perfectly complement a lifted stance, you’re in the right place. Truck, SUV, or Jeep?",
    "no_results": "I didn’t find a perfect match in our live inventory right now, but I’ve got plenty of similar styles that would look incredible on your build. Should we try adjusting the finish or size?"
}
