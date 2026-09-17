import hashlib
import hmac
import json
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal, engine
from app.models import Booking, BookingStatus, LedgerTransaction, Payment, ProfessionalProfile, Role, Service, ServiceType, User
from app.webhook_processing import WebhookProcessingError, process_paystack_webhook

class PaystackWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self): await engine.dispose()

    async def _payment(self):
        async with SessionLocal() as session:
            c=User(email=f"ps-c-{uuid.uuid4()}@example.com",password_hash="x",role=Role.customer,display_name="C"); p=User(email=f"ps-p-{uuid.uuid4()}@example.com",password_hash="x",role=Role.professional,display_name="P"); session.add_all([c,p]); await session.flush()
            profile=ProfessionalProfile(user_id=p.id,headline="P",bio="P",years_experience=1); session.add(profile); await session.flush()
            service=Service(professional_id=profile.id,name="S",service_type=ServiceType.fixed,price_ngn=5000,duration_minutes=60); session.add(service); await session.flush()
            booking=Booking(customer_id=c.id,professional_id=profile.id,service_id=service.id,status=BookingStatus.pending,starts_at=datetime.now(timezone.utc)+timedelta(days=2),total_ngn=5000); session.add(booking); await session.flush()
            payment=Payment(booking_id=booking.id,provider="paystack",provider_reference=f"ps_{uuid.uuid4().hex}",status="pending",amount_ngn=5000,currency="NGN",idempotency_key=f"ps-payment:{uuid.uuid4()}"); session.add(payment); await session.commit(); return payment.id,payment.provider_reference

    @staticmethod
    def body(reference, status="success", amount=500000, currency="NGN", event_id=None):
        return json.dumps({"event":"charge.success","data":{"id":event_id or uuid.uuid4().hex,"reference":reference,"amount":amount,"currency":currency,"status":status}}).encode()

    async def test_sha512_success_duplicate_and_invalid_signature(self):
        payment_id, reference = await self._payment(); body=self.body(reference); sig=hmac.new(b"sk_test",body,hashlib.sha512).hexdigest()
        with patch.object(settings,"paystack_secret_key","sk_test"):
            async with SessionLocal() as session:
                result=await process_paystack_webhook(session,body,sig); self.assertTrue(result.processed)
            async with SessionLocal() as session:
                duplicate=await process_paystack_webhook(session,body,sig); self.assertTrue(duplicate.duplicate)
        async with SessionLocal() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(LedgerTransaction).where(LedgerTransaction.source_id==payment_id)),1)
        with patch.object(settings,"paystack_secret_key","sk_test"):
            async with SessionLocal() as session:
                with self.assertRaises(WebhookProcessingError): await process_paystack_webhook(session,body,"bad")

    async def test_amount_reference_currency_validation(self):
        _, reference = await self._payment()
        with patch.object(settings,"paystack_secret_key","sk_test"):
            for kwargs in ({"amount":499900},{"currency":"USD"},{"reference":"wrong"}):
                candidate_reference = kwargs.pop("reference", reference)
                body=self.body(candidate_reference,**kwargs); sig=hmac.new(b"sk_test",body,hashlib.sha512).hexdigest()
                async with SessionLocal() as session:
                    with self.assertRaises(WebhookProcessingError): await process_paystack_webhook(session,body,sig)

if __name__ == "__main__": unittest.main()
