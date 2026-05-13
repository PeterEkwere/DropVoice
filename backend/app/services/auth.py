from itsdangerous import BadSignature, URLSafeSerializer

from app.config import get_settings


def build_serializer() -> URLSafeSerializer:
    settings = get_settings()
    return URLSafeSerializer(settings.device_token_secret, salt="dropvoice-device")


def issue_device_token(device_id: str) -> str:
    return build_serializer().dumps({"device_id": device_id})


def read_device_token(token: str) -> str:
    try:
        payload = build_serializer().loads(token)
    except BadSignature as exc:
        raise ValueError("Invalid device token.") from exc
    device_id = payload.get("device_id")
    if not device_id:
        raise ValueError("Invalid device token.")
    return device_id

