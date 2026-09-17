from dataclasses import dataclass
from typing import Protocol
import hashlib
import hmac
import httpx

from .config import settings

@dataclass
class CheckoutSession:
    provider: str
    reference: str
    checkout_url: str | None = None
    access_code: str | None = None
    status: str | None = None

@dataclass
class VerificationResult:
    provider: str
    reference: str
    status: str
    amount_ngn: int
    currency: str
    raw: dict

@dataclass
class TransferRecipient:
    provider: str
    recipient_code: str
    raw: dict

@dataclass
class TransferResult:
    provider: str
    transfer_code: str | None
    reference: str
    status: str
    amount_ngn: int
    currency: str
    raw: dict

@dataclass
class ProviderRefundResult:
    provider: str
    provider_reference: str | None
    status: str
    amount_ngn: int
    currency: str
    raw: dict

class ProviderError(RuntimeError):
    pass

def map_paystack_status(status: str) -> str:
    value = (status or "").lower()
    if value == "success": return "paid"
    if value in {"failed", "abandoned"}: return "failed"
    if value in {"pending", "ongoing", "processing", "queued"}: return "pending"
    if value == "reversed": return "reversed"
    return "unknown"

class PaymentProvider(Protocol):
    async def create_checkout(self, amount_ngn: int, email: str, reference: str) -> CheckoutSession: ...
    async def refund(self, reference: str | None, amount_ngn: int | None) -> ProviderRefundResult: ...
    async def verify_transaction(self, reference: str) -> VerificationResult: ...
    async def create_transfer_recipient(self, account_name: str, account_reference: str, bank_code: str | None = None) -> TransferRecipient: ...
    async def initiate_transfer(self, amount_ngn: int, recipient_code: str, reference: str, reason: str | None = None) -> TransferResult: ...
    async def verify_transfer(self, transfer_code: str) -> TransferResult: ...

class PendingProvider:
    """Safe adapter: never claims to have collected money. Replace with a real NGN provider adapter."""
    async def create_checkout(self, amount_ngn: int, email: str, reference: str) -> CheckoutSession:
        return CheckoutSession(provider="pending", reference=reference, checkout_url=None)
    async def refund(self, reference: str | None, amount_ngn: int | None) -> ProviderRefundResult:
        raise ProviderError("Pending provider has no refund support")
    async def verify_transaction(self, reference: str) -> VerificationResult:
        raise ProviderError("Pending provider has no transaction verification")
    async def create_transfer_recipient(self, account_name: str, account_reference: str, bank_code: str | None = None) -> TransferRecipient:
        raise ProviderError("Pending provider has no transfer recipients")
    async def initiate_transfer(self, amount_ngn: int, recipient_code: str, reference: str, reason: str | None = None) -> TransferResult:
        raise ProviderError("Pending provider has no transfers")
    async def verify_transfer(self, transfer_code: str) -> TransferResult:
        raise ProviderError("Pending provider has no transfer verification")


class PaystackProvider:
    """Paystack sandbox adapter; the secret key is server-side only."""
    provider_name = "paystack"

    def __init__(self, secret_key: str | None = None, base_url: str | None = None, client=None):
        self.secret_key = secret_key if secret_key is not None else settings.paystack_secret_key
        self.base_url = (base_url or settings.paystack_base_url).rstrip("/")
        self.client = client
        if not self.secret_key:
            raise ProviderError("Paystack is not configured")

    @staticmethod
    def amount_to_kobo(amount_ngn: int) -> int:
        if isinstance(amount_ngn, bool) or not isinstance(amount_ngn, int) or amount_ngn <= 0:
            raise ProviderError("Amount must be a positive integer NGN value")
        return amount_ngn * 100

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret_key}", "Content-Type": "application/json"}

    async def _request(self, method: str, path: str, **kwargs):
        try:
            if self.client is not None:
                response = await self.client.request(method, f"{self.base_url}{path}", headers=self._headers(), timeout=15, **kwargs)
            else:
                async with httpx.AsyncClient() as client:
                    response = await client.request(method, f"{self.base_url}{path}", headers=self._headers(), timeout=15, **kwargs)
        except httpx.HTTPError as exc:
            raise ProviderError("Paystack network request failed") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise ProviderError("Paystack returned malformed JSON") from exc
        if response.status_code >= 400 or not data.get("status"):
            raise ProviderError(str(data.get("message") or "Paystack request failed"))
        return data

    async def create_checkout(self, amount_ngn: int, email: str, reference: str) -> CheckoutSession:
        data = await self._request("POST", "/transaction/initialize", json={
            "amount": self.amount_to_kobo(amount_ngn), "email": email, "reference": reference,
            "currency": "NGN", "metadata": {"dopenexa_reference": reference},
        })
        result = data.get("data") or {}
        provider_reference = result.get("reference") or reference
        authorization_url = result.get("authorization_url")
        if not authorization_url:
            raise ProviderError("Paystack response did not include an authorization URL")
        return CheckoutSession(provider="paystack", reference=provider_reference, checkout_url=authorization_url,
                               access_code=result.get("access_code"), status=result.get("status"))

    async def refund(self, reference: str | None, amount_ngn: int | None) -> ProviderRefundResult:
        if not reference:
            raise ProviderError("Paystack refund requires the original transaction reference")
        body = {"transaction": reference}
        if amount_ngn is not None:
            body["amount"] = self.amount_to_kobo(amount_ngn)
        data = await self._request("POST", "/refund", json=body)
        result = data.get("data") or {}
        raw_amount = result.get("amount")
        if raw_amount is None:
            raise ProviderError("Paystack refund response has no valid amount")
        try:
            parsed_amount = int(raw_amount) // 100
        except (TypeError, ValueError) as exc:
            raise ProviderError("Paystack refund response has no valid amount") from exc
        if parsed_amount <= 0:
            raise ProviderError("Paystack refund response has no valid amount")
        return ProviderRefundResult(provider="paystack", provider_reference=str(result.get("id") or result.get("refund_id") or "") or None,
                                    status=str(result.get("status") or "pending").lower(), amount_ngn=parsed_amount,
                                    currency=str(result.get("currency") or "NGN").upper(), raw=result)

    async def verify_refund(self, provider_reference: str) -> ProviderRefundResult:
        data = await self._request("GET", f"/refund/{provider_reference}")
        result = data.get("data") or {}
        raw_amount = result.get("amount")
        try: parsed_amount = int(raw_amount) // 100
        except (TypeError, ValueError) as exc: raise ProviderError("Paystack refund response has no valid amount") from exc
        return ProviderRefundResult(provider="paystack", provider_reference=str(result.get("id") or provider_reference),
                                    status=str(result.get("status") or "pending").lower(), amount_ngn=parsed_amount,
                                    currency=str(result.get("currency") or "NGN").upper(), raw=result)

    async def create_transfer_recipient(self, account_name: str, account_reference: str, bank_code: str | None = None) -> TransferRecipient:
        if not bank_code:
            raise ProviderError("Paystack bank code is required to create a transfer recipient")
        data = await self._request("POST", "/transferrecipient", json={
            "type": "nuban", "name": account_name, "account_number": account_reference,
            "bank_code": bank_code, "currency": "NGN",
        })
        result = data.get("data") or {}
        code = result.get("recipient_code")
        if not code:
            raise ProviderError("Paystack response did not include a recipient code")
        return TransferRecipient(provider="paystack", recipient_code=str(code), raw=result)

    async def initiate_transfer(self, amount_ngn: int, recipient_code: str, reference: str, reason: str | None = None) -> TransferResult:
        data = await self._request("POST", "/transfer", json={
            "source": "balance", "amount": self.amount_to_kobo(amount_ngn),
            "recipient": recipient_code, "reference": reference,
            "reason": reason or "Dopenexa professional payout",
            "currency": "NGN",
        })
        result = data.get("data") or {}
        return self._transfer_result(result, reference)

    async def verify_transfer(self, transfer_code: str) -> TransferResult:
        data = await self._request("GET", f"/transfer/verify/{transfer_code}")
        result = data.get("data") or {}
        return self._transfer_result(result, str(result.get("reference") or transfer_code))

    def _transfer_result(self, result: dict, fallback_reference: str) -> TransferResult:
        try:
            amount_ngn = int(result.get("amount", 0)) // 100
        except (TypeError, ValueError) as exc:
            raise ProviderError("Paystack transfer response has no valid amount") from exc
        if amount_ngn <= 0:
            raise ProviderError("Paystack transfer response has no valid amount")
        return TransferResult(provider="paystack", transfer_code=result.get("transfer_code"),
                              reference=str(result.get("reference") or fallback_reference),
                              status=str(result.get("status") or "").lower(), amount_ngn=amount_ngn,
                              currency=str(result.get("currency") or "NGN").upper(), raw=result)

    async def verify_transaction(self, reference: str) -> VerificationResult:
        data = await self._request("GET", f"/transaction/verify/{reference}")
        result = data.get("data") or {}
        try:
            amount_kobo = int(result["amount"])
            amount_ngn = amount_kobo // 100
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Paystack verification response has no valid amount") from exc
        return VerificationResult(provider="paystack", reference=str(result.get("reference") or reference),
                                  status=map_paystack_status(str(result.get("status") or "")), amount_ngn=amount_ngn,
                                  currency=str(result.get("currency") or "").upper(), raw=result)

    @staticmethod
    def verify_webhook_signature(payload: bytes, signature: str | None, secret_key: str) -> None:
        expected = hmac.new(secret_key.encode(), payload, hashlib.sha512).hexdigest()
        if not signature or not hmac.compare_digest(expected, signature):
            raise ProviderError("Invalid Paystack webhook signature")


def configured_payment_provider():
    if settings.payment_provider.lower() == "paystack" and settings.paystack_secret_key:
        return PaystackProvider()
    return PendingProvider()
