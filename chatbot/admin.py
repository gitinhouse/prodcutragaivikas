from django.contrib import admin
from .models import Fitment, Product

@admin.register(Fitment)
class FitmentAdmin(admin.ModelAdmin):
    list_display = ('make', 'model', 'year_from', 'year_to', 'product')
    search_fields = ('make', 'model', 'product__name')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'price', 'part_number')
    search_fields = ('name', 'part_number')
