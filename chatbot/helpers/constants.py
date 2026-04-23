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
    "Welcome to the Studio. I'm Sebastian — your wheel specialist. To get us started: are you outfitting a Truck, SUV, or Jeep?",
    "Hey there. Sebastian here. Looking to upgrade your vehicle's stance with some premium wheels? What are you driving?",
    "Welcome. I'm Sebastian. Let's get your build dialed in. Are we working on a Truck, SUV, or Jeep today?"
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
    "hard_block": "That's outside my wheelhouse (pun intended). What can I help you with for your build?",
    "pivot_tires": "Tires aren't our lane, but if you're looking to upgrade the rims while you're at it — I've got you. What are you driving?",
    "pivot_lift": "Lift kits we leave to the suspension guys. But if you want wheels that match the lifted stance — that's exactly what I do. Truck, SUV, or Jeep?",
    "no_results": "I couldn’t find an exact match, but I can suggest close options or adjust filters to better fit your needs."
}
