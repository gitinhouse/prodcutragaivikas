from django.contrib import admin
from .models import Fitment, Product, Brand, VehicleTypeLimit, BoltPatternRule

@admin.register(Fitment)
class FitmentAdmin(admin.ModelAdmin):
    list_display = ('make', 'model', 'year_from', 'year_to', 'product')
    search_fields = ('make', 'model', 'product__name')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'price', 'part_number')
    search_fields = ('name', 'part_number')
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_wheel_brand', 'website')
    list_filter = ('is_wheel_brand',)
    search_fields = ('name',)

@admin.register(VehicleTypeLimit)
class VehicleTypeLimitAdmin(admin.ModelAdmin):
    list_display = ('vehicle_type', 'max_diameter', 'max_width')

@admin.register(BoltPatternRule)
class BoltPatternRuleAdmin(admin.ModelAdmin):
    list_display = ('make', 'model', 'patterns')
    search_fields = ('make', 'model')
