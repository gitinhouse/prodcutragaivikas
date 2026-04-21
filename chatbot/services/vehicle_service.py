import re
import difflib

class VehicleService:
    """
    Fuzzy Matching Engine for Vehicle Resolution.
    Normalized DB matching without heavy overhead.
    """

    KNOWN_MODELS = {
        "f150": "F-150",
        "f-150": "F-150",
        "f 150": "F-150",
        "f250": "F-250",
        "f-250": "F-250",
        "1500": "1500",
        "silverado": "Silverado",
        "civic": "Civic",
        "wrx": "WRX",
        "tundra": "Tundra",
        "tacoma": "Tacoma",
        "camry": "Camry",
        "corolla": "Corolla",
        "accord": "Accord",
        "mustang": "Mustang",
        "bronco": "Bronco",
        "a4": "A4",
        "3 series": "3 Series",
        "3-series": "3 Series"
    }

    KNOWN_MAKES = {
        "ford": "Ford",
        "chevy": "Chevrolet",
        "chevrolet": "Chevrolet",
        "honda": "Honda",
        "toyota": "Toyota",
        "subaru": "Subaru",
        "dodge": "Dodge",
        "ram": "Ram",
        "gmc": "GMC",
        "audi": "Audi",
        "bmw": "BMW"
    }

    @classmethod
    def resolve_vehicle(cls, user_query: str) -> dict:
        """
        Extracts and fuzzy matches Year, Make, Model, and inferred Type.
        """
        query_lower = user_query.lower()
        result = {}

        # 1. Year Extraction
        # Look for 4 digits starting with 19 or 20, or an apostrophe followed by 2 digits like '19
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', query_lower)
        if year_match:
            result['year'] = int(year_match.group(1))
        else:
            short_year_match = re.search(r"'(\d{2})\b", query_lower)
            if short_year_match:
                yy = int(short_year_match.group(1))
                result['year'] = 1900 + yy if yy > 50 else 2000 + yy

        # 2. Make & Model Fuzzy Match
        words = query_lower.replace("'", "").split()
        
        extracted_make = None
        extracted_model = None

        for word in words:
            # Check makes
            closest_make = difflib.get_close_matches(word, cls.KNOWN_MAKES.keys(), n=1, cutoff=0.8)
            if closest_make and not extracted_make:
                extracted_make = cls.KNOWN_MAKES[closest_make[0]]
            
            # Check models
            closest_model = difflib.get_close_matches(word, cls.KNOWN_MODELS.keys(), n=1, cutoff=0.8)
            if closest_model and not extracted_model:
                extracted_model = cls.KNOWN_MODELS[closest_model[0]]

        if extracted_make:
            result['make'] = extracted_make
        if extracted_model:
            result['model'] = extracted_model

        # 3. Type Inference
        if extracted_model in ["F-150", "1500", "Silverado", "Tundra", "Tacoma", "F-250"]:
            result['vehicle_type'] = "Truck"
        elif extracted_model in ["Bronco"]:
            result['vehicle_type'] = "SUV"
        elif extracted_model in ["Civic", "WRX", "Camry", "Corolla", "Accord", "Mustang"]:
            result['vehicle_type'] = "Car"
        elif "truck" in query_lower:
             result['vehicle_type'] = "Truck"
        elif "suv" in query_lower:
             result['vehicle_type'] = "SUV"
        elif "jeep" in query_lower:
             result['vehicle_type'] = "SUV"

        return result
