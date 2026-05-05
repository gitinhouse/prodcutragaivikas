import os
import requests
import logging
from django.conf import settings

logger = logging.getLogger("chatbot.services.fitment_api")

class FitmentApiService:
    """
    Direct interface with Fitment Group API v1.1.
    Handles vehicle ID resolution and technical spec retrieval.
    """
    
    BASE_URL = "https://api.fitmentatlas.com/v1.1/services/Vehicles"
    
    @classmethod
    def _get_headers(cls):
        api_key = os.getenv("FG_API_KEY")
        if not api_key:
            logger.error("FG_API_KEY not found in environment.")
            raise ValueError("FG_API_KEY is missing.")
        return {"FG-ApiKey": api_key}

    @classmethod
    def get_fitment_specs(cls, year_id: int, make_id: str, model_id: str) -> dict:
        """
        Orchestrates API calls to get precise bolt pattern and plus sizes.
        """
        try:
            # 1. Get FMK ID from Smart Sizes
            smart_url = f"{cls.BASE_URL}/smartsizes/"
            params = {
                "YearId": year_id,
                "MakeId": make_id,
                "ModelId": model_id,
                "ProductType": "wheel"
            }
            
            logger.info(f"Calling smartsizes API for Year:{year_id}, Make:{make_id}, Model:{model_id}")
            response = requests.get(smart_url, params=params, headers=cls._get_headers())
            response.raise_for_status()
            data = response.json()
            
            if not data.get("success") or not data.get("result"):
                logger.warning(f"No results found in smartsizes for {params}")
                return {}
            
            # Get fmk from first object as requested
            fmk_id = data["result"][0].get("fmk")
            if not fmk_id:
                logger.warning("No fmk ID found in first result.")
                return {}
            
            # 2. Get Vehicle Details
            detail_url = f"{cls.BASE_URL}/{fmk_id}"
            logger.info(f"Calling vehicle details API for fmk:{fmk_id}")
            response = requests.get(detail_url, headers=cls._get_headers())
            response.raise_for_status()
            detail_data = response.json()
            
            if not detail_data.get("success") or not detail_data.get("result"):
                logger.warning(f"No details found for fmk:{fmk_id}")
                return {}
            
            result = detail_data["result"]
            chassis = result.get("vehicleChassis", {})
            model_data = result.get("vehicleModel", {})
            
            # Extract Bolt Pattern
            bolt_pattern = chassis.get("boltPattern")
            
            # Extract Plus Sizes
            plus_sizes = []
            
            # 1. Add Base Size from vehicleModel
            base_w = model_data.get("rimWidth")
            base_d = model_data.get("rimDiameter")
            if base_w and base_d:
                plus_sizes.append({
                    "rimWidth": base_w,
                    "rimDiameter": base_d,
                    "rimSize": f"{base_w}x{base_d}"
                })

            # 2. Add all from vehiclePlusSizes
            for ps in chassis.get("vehiclePlusSizes", []):
                plus_sizes.append({
                    "rimWidth": ps.get("rimWidth"),
                    "rimDiameter": ps.get("rimDiameter"),
                    "rimSize": ps.get("rimSize")
                })
            
            return {
                "bolt_pattern": bolt_pattern,
                "plus_sizes": plus_sizes,
                "fmk_id": fmk_id
            }
            
        except Exception as e:
            logger.error(f"Fitment Group API error: {str(e)}")
            return {}
