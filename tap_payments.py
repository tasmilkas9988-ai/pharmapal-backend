import httpx
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
import os

logger = logging.getLogger(__name__)

class TapPaymentsClient:
    def __init__(self):
        self.base_url = os.environ.get('TAP_API_BASE_URL', 'https://api.tap.company')
        self.secret_key = os.environ.get('TAP_SECRET_KEY')
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
    
    async def create_charge(
        self,
        amount: Decimal,
        currency: str,
        source_id: str,
        customer_name: str,
        customer_email: str,
        description: str,
        redirect_url: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a charge using Tap Payments API"""
        
        payload = {
            "amount": float(amount),
            "currency": currency,
            "description": description,
            "customer": {
                "first_name": customer_name.split()[0] if customer_name else "",
                "last_name": " ".join(customer_name.split()[1:]) if len(customer_name.split()) > 1 else "",
                "email": customer_email
            },
            "source": {
                "id": source_id
            },
            "redirect": {
                "url": redirect_url
            },
            "metadata": metadata or {}
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/v2/charges",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Tap API error creating charge: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise Exception(f"Payment processing failed: {str(e)}")
    
    async def retrieve_charge(self, charge_id: str) -> Dict[str, Any]:
        """Retrieve charge details"""
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/v2/charges/{charge_id}",
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Tap API error retrieving charge: {str(e)}")
            raise Exception(f"Could not retrieve charge status: {str(e)}")
