from __future__ import annotations

import hashlib
import hmac
import json

import httpx

from app.config import get_settings


class OPayClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.opay_merchant_id and self.settings.opay_public_key and self.settings.opay_private_key)

    async def create_cashier(
        self,
        *,
        reference: str,
        amount_kobo: int,
        return_url: str,
        cancel_url: str,
        visit_source: str,
        pay_method: str | None,
        customer_name: str | None,
        customer_email: str | None,
        customer_phone: str | None,
        customer_user_id: str | None,
    ) -> dict:
        if not self.configured:
            raise RuntimeError("OPay is not configured.")

        payload = {
            "country": "NG",
            "reference": reference,
            "amount": {
                "total": amount_kobo,
                "currency": "NGN",
            },
            "returnUrl": return_url,
            "cancelUrl": cancel_url,
            "callbackUrl": self.settings.opay_callback_url or None,
            "payMethod": pay_method,
            "customerVisitSource": visit_source,
            "evokeOpay": visit_source in {"IOS", "ANDROID"},
            "expireAt": 30,
            "product": {
                "name": "DropVoice Wallet Top-up",
                "description": "Wallet credit for DropVoice voice generation",
            },
            "userInfo": {
                "userName": customer_name,
                "userEmail": customer_email,
                "userMobile": customer_phone,
                "userId": customer_user_id,
            },
        }

        clean_payload = scrub_none(payload)
        headers = {
            "Authorization": f"Bearer {self.settings.opay_public_key}",
            "MerchantId": self.settings.opay_merchant_id,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(base_url=self.settings.opay_api_base_url, timeout=60.0) as client:
            response = await client.post("/api/v1/international/cashier/create", headers=headers, json=clean_payload)
            response.raise_for_status()
            return response.json()

    async def query_status(self, reference: str) -> dict:
        if not self.configured:
            raise RuntimeError("OPay is not configured.")

        payload = {"reference": reference, "country": "NG"}
        signature = self.sign_payload(payload)
        headers = {
            "MerchantId": self.settings.opay_merchant_id,
            "Authorization": f"Bearer {signature}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(base_url=self.settings.opay_api_base_url, timeout=60.0) as client:
            response = await client.post("/api/v1/international/cashier/status", headers=headers, json=payload)
            response.raise_for_status()
            return response.json()

    def verify_callback_signature(self, payload: dict) -> bool:
        provided = payload.get("sha512")
        callback_body = payload.get("payload")
        if not provided or callback_body is None:
            return False

        raw_payload = json.dumps(callback_body, separators=(",", ":"), ensure_ascii=False)
        expected = hmac.new(
            self.settings.opay_private_key.encode("utf-8"),
            raw_payload.encode("utf-8"),
            hashlib.sha3_512,
        ).hexdigest()
        return hmac.compare_digest(provided.lower(), expected.lower())

    def sign_payload(self, payload: dict) -> str:
        canonical = canonical_json(payload)
        return hmac.new(
            self.settings.opay_private_key.encode("utf-8"),
            canonical.encode("utf-8"),
            hashlib.sha512,
        ).hexdigest()


def scrub_none(data: dict) -> dict:
    output: dict = {}
    for key, value in data.items():
        if isinstance(value, dict):
            nested = scrub_none(value)
            if nested:
                output[key] = nested
            continue
        if value is not None:
            output[key] = value
    return output


def canonical_json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, sort_keys=True)
