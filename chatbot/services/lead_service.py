from typing import Optional
from asgiref.sync import sync_to_async
from chatbot.models import Lead

class ServiceError(Exception):
    pass

class DuplicateLeadError(ServiceError):
    pass

class LeadService:
    """
    Business logic for customer lead management.
    Hardened for Async: All DB operations wrapped in sync_to_async.
    """

    @staticmethod
    async def create_lead(first_name: str, email: str) -> Lead:
        """
        Ensures PII-safe lead creation with unique email validation.
        Async-Safe.
        """
        def _check_and_create():
            if Lead.objects.filter(email=email).exists():
                raise DuplicateLeadError(f"Lead with email {email} already exists.")
                
            return Lead.objects.create(
                first_name=first_name,
                email=email
            )
            
        return await sync_to_async(_check_and_create)()

    @staticmethod
    async def get_lead_by_email(email: str) -> Optional[Lead]:
        """
        Retrieves a lead by email. Async-Safe.
        """
        return await sync_to_async(lambda: Lead.objects.filter(email=email).first())()
