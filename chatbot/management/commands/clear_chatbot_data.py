from django.core.management.base import BaseCommand
from chatbot.models import Order, Product, Category, Brand, Lead

class Command(BaseCommand):
    help = 'Clears all chatbot data while preserving migrations and admin accounts.'

    def handle(self, *args, **options):
        self.stdout.write('Clearing chatbot data...')
        
        # Deletion order matters if on_delete=models.PROTECT is used
        Order.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        Brand.objects.all().delete()
        Lead.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS('Successfully cleared all chatbot tables.'))
