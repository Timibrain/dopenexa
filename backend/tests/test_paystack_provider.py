import hashlib
import hmac
import json
import unittest
import uuid
from unittest.mock import patch

from app.config import settings
from app.payment_provider import PaystackProvider, ProviderError, map_paystack_status


class FakeResponse:
    def __init__(self, payload, status_code=200): self.payload, self.status_code = payload, status_code
    def json(self): return self.payload

class FakeClient:
    def __init__(self, payload): self.payload, self.calls = payload, []
    async def request(self, method, url, **kwargs): self.calls.append((method, url, kwargs)); return FakeResponse(self.payload)

class PaystackProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialization_converts_ngn_to_kobo_and_parses_response(self):
        client = FakeClient({"status": True, "data": {"reference": "dpx_ref", "authorization_url": "https://paystack.test/checkout", "access_code": "abc"}})
        provider = PaystackProvider(secret_key="sk_test", base_url="https://api.test", client=client)
        checkout = await provider.create_checkout(5000, "customer@example.com", "dpx_ref")
        payload = client.calls[0][2]["json"]
        self.assertEqual(payload["amount"], 500000); self.assertEqual(payload["currency"], "NGN"); self.assertEqual(payload["email"], "customer@example.com")
        self.assertEqual((checkout.provider, checkout.reference, checkout.checkout_url, checkout.access_code), ("paystack", "dpx_ref", "https://paystack.test/checkout", "abc"))

    async def test_verification_mapping_and_malformed_response(self):
        client = FakeClient({"status": True, "data": {"reference": "dpx_ref", "status": "success", "amount": 500000, "currency": "NGN"}})
        result = await PaystackProvider(secret_key="sk_test", client=client).verify_transaction("dpx_ref")
        self.assertEqual((result.status, result.amount_ngn, result.currency), ("paid", 5000, "NGN"))
        bad = FakeClient({"status": True, "data": {"reference": "dpx_ref"}})
        with self.assertRaises(ProviderError): await PaystackProvider(secret_key="sk_test", client=bad).verify_transaction("dpx_ref")

    async def test_signature_and_status_mapping(self):
        body = b'{"event":"charge.success"}'
        signature = hmac.new(b"sk_test", body, hashlib.sha512).hexdigest()
        PaystackProvider.verify_webhook_signature(body, signature, "sk_test")
        with self.assertRaises(ProviderError): PaystackProvider.verify_webhook_signature(body, "bad", "sk_test")
        self.assertEqual({s: map_paystack_status(s) for s in ["success", "failed", "abandoned", "pending", "ongoing", "processing", "queued", "reversed"]}, {"success":"paid","failed":"failed","abandoned":"failed","pending":"pending","ongoing":"pending","processing":"pending","queued":"pending","reversed":"reversed"})

    async def test_network_failure_is_provider_error(self):
        import httpx
        class Failing:
            async def request(self, *args, **kwargs): raise httpx.ConnectError("offline")
        with self.assertRaises(ProviderError): await PaystackProvider(secret_key="sk_test", client=Failing()).verify_transaction("ref")

    async def test_transfer_recipient_and_transfer_payloads(self):
        recipient_client = FakeClient({"status": True, "data": {"recipient_code": "RCP_test"}})
        provider = PaystackProvider(secret_key="sk_test", client=recipient_client)
        recipient = await provider.create_transfer_recipient("Test Professional", "0000000000", "058")
        self.assertEqual(recipient.recipient_code, "RCP_test")
        self.assertEqual(recipient_client.calls[0][2]["json"], {"type":"nuban","name":"Test Professional","account_number":"0000000000","bank_code":"058","currency":"NGN"})
        transfer_client = FakeClient({"status": True, "data": {"transfer_code": "TRF_test", "reference": "dpx_payout_test", "status": "pending", "amount": 300000, "currency": "NGN"}})
        transfer = await PaystackProvider(secret_key="sk_test", client=transfer_client).initiate_transfer(3000, "RCP_test", "dpx_payout_test", "Dopenexa payout")
        self.assertEqual((transfer.transfer_code, transfer.reference, transfer.amount_ngn, transfer.status), ("TRF_test", "dpx_payout_test", 3000, "pending"))
        payload = transfer_client.calls[0][2]["json"]
        self.assertEqual((payload["amount"], payload["recipient"], payload["reference"], payload["currency"]), (300000, "RCP_test", "dpx_payout_test", "NGN"))

    async def test_transfer_verification_parsing(self):
        client = FakeClient({"status": True, "data": {"transfer_code": "TRF_test", "reference": "dpx_payout_test", "status": "success", "amount": 300000, "currency": "NGN"}})
        result = await PaystackProvider(secret_key="sk_test", client=client).verify_transfer("TRF_test")
        self.assertEqual((result.transfer_code, result.status, result.amount_ngn, result.currency), ("TRF_test", "success", 3000, "NGN"))

    async def test_partial_and_full_refund_payloads(self):
        client = FakeClient({"status": True, "data": {"id": "RF_test", "status": "pending", "amount": 100000, "currency": "NGN"}})
        provider = PaystackProvider(secret_key="sk_test", client=client)
        partial = await provider.refund("dpx_payment", 1000)
        self.assertEqual((partial.provider_reference, partial.amount_ngn, partial.status), ("RF_test", 1000, "pending"))
        self.assertEqual(client.calls[0][2]["json"], {"transaction":"dpx_payment","amount":100000})
        full_client = FakeClient({"status": True, "data": {"id": "RF_full", "status": "processing", "amount": 500000, "currency": "NGN"}})
        await PaystackProvider(secret_key="sk_test", client=full_client).refund("dpx_payment", None)
        self.assertEqual(full_client.calls[0][2]["json"], {"transaction":"dpx_payment"})

    async def test_refund_network_and_malformed_response(self):
        import httpx
        class Failing:
            async def request(self, *args, **kwargs): raise httpx.ConnectError("offline")
        with self.assertRaises(ProviderError): await PaystackProvider(secret_key="sk_test", client=Failing()).refund("ref", 1000)
        bad = FakeClient({"status": True, "data": {"id": "RF_bad", "status": "pending"}})
        with self.assertRaises(ProviderError): await PaystackProvider(secret_key="sk_test", client=bad).refund("ref", 1000)

    def test_missing_configuration_uses_pending_fallback(self):
        with patch.object(settings, "payment_provider", "paystack"), patch.object(settings, "paystack_secret_key", ""):
            from app.payment_provider import configured_payment_provider, PendingProvider
            self.assertIsInstance(configured_payment_provider(), PendingProvider)

if __name__ == "__main__": unittest.main()
