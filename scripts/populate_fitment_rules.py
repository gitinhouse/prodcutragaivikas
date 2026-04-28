import os
import django
import sys

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from chatbot.models import Brand, VehicleTypeLimit, BoltPatternRule

def populate_data():
    print("Populating static data into the database...")

    # 1. Wheel Brands
    wheel_brands = ["bbs", "vossen", "fuel", "rohana", "tsw", "dirty life", "method", "american", "black rhino", "kmc", "niche", "rotiform", "savini", "hostile", "moto metal", "xd", "asanti"]
    for brand_name in wheel_brands:
        brand, created = Brand.objects.get_or_create(name=brand_name)
        brand.is_wheel_brand = True
        brand.save()
        if created:
            print(f"Created brand: {brand_name}")
        else:
            print(f"Updated brand: {brand_name}")

    # 2. Vehicle Type Limits
    limits = {
        "sedan": {"max_diameter": 20, "max_width": 9.5},
        "coupe": {"max_diameter": 20, "max_width": 9.5},
        "hatchback": {"max_diameter": 19, "max_width": 8.5},
        "suv": {"max_diameter": 26, "max_width": 12.0},
        "truck": {"max_diameter": 28, "max_width": 14.0},
        "jeep": {"max_diameter": 24, "max_width": 12.0}
    }
    for v_type, limit in limits.items():
        obj, created = VehicleTypeLimit.objects.get_or_create(
            vehicle_type=v_type,
            defaults={
                'max_diameter': limit['max_diameter'],
                'max_width': limit['max_width']
            }
        )
        if not created:
            obj.max_diameter = limit['max_diameter']
            obj.max_width = limit['max_width']
            obj.save()
        print(f"{'Created' if created else 'Updated'} limit for: {v_type}")

    # 3. Bolt Pattern Rules (Make-level)
    make_patterns = {
        "ford": ["6x135", "5x108", "5x114.3"],
        "toyota": ["6x139.7", "5x114.3", "5x150"],
        "bmw": ["5x120", "5x112"],
        "audi": ["5x112"],
        "mercedes": ["5x112"],
        "honda": ["5x114.3", "5x120"],
        "tesla": ["5x114.3", "5x120"],
        "jeep": ["5x127", "5x114.3"]
    }
    for make, patterns in make_patterns.items():
        obj, created = BoltPatternRule.objects.get_or_create(
            make=make,
            model=None,
            defaults={'patterns': patterns}
        )
        if not created:
            obj.patterns = patterns
            obj.save()
        print(f"{'Created' if created else 'Updated'} rule for make: {make}")

    # 4. Bolt Pattern Rules (Model-level)
    model_patterns = {
        "honda": {
            "civic": ["5x114.3"],
            "accord": ["5x114.3"],
            "cr-v": ["5x114.3"],
            "odyssey": ["5x120"],
            "pilot": ["5x120"]
        },
        "tesla": {
            "model 3": ["5x114.3"],
            "model y": ["5x114.3"],
            "model s": ["5x120"],
            "model x": ["5x120"]
        }
    }
    for make, models in model_patterns.items():
        for model, patterns in models.items():
            obj, created = BoltPatternRule.objects.get_or_create(
                make=make,
                model=model,
                defaults={'patterns': patterns}
            )
            if not created:
                obj.patterns = patterns
                obj.save()
            print(f"{'Created' if created else 'Updated'} rule for model: {make} {model}")

    print("\nData population complete!")

if __name__ == "__main__":
    populate_data()
