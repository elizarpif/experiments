import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl


class TelegramAuthError(Exception):
    pass


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> dict:
    """Verify Mini App initData per https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app"""
    if not init_data or not bot_token:
        raise TelegramAuthError("Некорректные данные авторизации")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("Отсутствует подпись Telegram")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        raise TelegramAuthError("Подпись Telegram не прошла проверку")

    try:
        auth_date = int(parsed.get("auth_date", "0"))
    except ValueError as exc:
        raise TelegramAuthError("Некорректная дата авторизации") from exc

    if auth_date <= 0 or time.time() - auth_date > max_age_seconds:
        raise TelegramAuthError("Сессия Telegram устарела, перезапустите приложение")

    raw_user = parsed.get("user")
    if not raw_user:
        raise TelegramAuthError("Данные пользователя Telegram отсутствуют")

    try:
        user = json.loads(raw_user)
    except json.JSONDecodeError as exc:
        raise TelegramAuthError("Некорректный профиль Telegram") from exc

    if not user.get("id"):
        raise TelegramAuthError("Некорректный идентификатор Telegram")

    return user
