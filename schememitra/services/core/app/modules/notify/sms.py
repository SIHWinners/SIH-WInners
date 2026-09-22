"""SMS adapters (spec §9.7). Templates come from the i18n catalogues and are DLT-shaped: fixed
text with short variables. Segment counting follows GSM-7 vs UCS-2 so Indic messages that need
more parts are visible in the admin SMS console.

ConsoleSms (SMS_MODE=console, SANDBOX) records the message and streams it to the admin phone
mockup. Msg91Sms / TwilioSms send for real behind env credentials."""

from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import httpx

from app.config import get_settings
from app.core import events

GSM7 = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
    "abcdefghijklmnopqrstuvwxyzäöñüà"
)


def segments(body: str) -> int:
    if all(ch in GSM7 for ch in body):
        return 1 if len(body) <= 160 else -(-len(body) // 153)
    units = len(body.encode("utf-16-le")) // 2
    return 1 if units <= 70 else -(-units // 67)


@dataclass
class SendResult:
    provider: str
    provider_msg_id: str | None
    status: str
    sandbox: bool


class SmsProvider(Protocol):
    async def send(self, to: str, body: str) -> SendResult: ...


# Recent console messages for the admin phone mockup (demo only; masked numbers).
CONSOLE_FEED: deque[dict[str, Any]] = deque(maxlen=200)


class ConsoleSms:
    async def send(self, to: str, body: str) -> SendResult:
        item = {"to": f"******{to[-4:]}", "body": body, "segments": segments(body),
                "at": datetime.now(UTC).isoformat(timespec="seconds"), "direction": "out"}
        CONSOLE_FEED.appendleft(item)
        events.publish("admin", "sms", item)
        return SendResult("console", None, "delivered", True)


class Msg91Sms:
    async def send(self, to: str, body: str) -> SendResult:
        s = get_settings()
        async with httpx.AsyncClient(timeout=s.external_timeout_s) as client:
            res = await client.post("https://control.msg91.com/api/v5/flow/", headers={"authkey": s.msg91_auth_key or ""},
                                    json={"mobiles": f"91{to}", "message": body})
            res.raise_for_status()
            return SendResult("msg91", res.json().get("request_id"), "sent", False)


class TwilioSms:
    async def send(self, to: str, body: str) -> SendResult:
        s = get_settings()
        url = f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json"
        async with httpx.AsyncClient(timeout=s.external_timeout_s) as client:
            res = await client.post(url, auth=(s.twilio_account_sid or "", s.twilio_auth_token or ""),
                                    data={"To": f"+91{to}", "From": s.twilio_from or "", "Body": body})
            res.raise_for_status()
            return SendResult("twilio", res.json().get("sid"), "sent", False)


def get_sms_provider() -> SmsProvider:
    mode = get_settings().sms_mode
    return Msg91Sms() if mode == "msg91" else TwilioSms() if mode == "twilio" else ConsoleSms()
