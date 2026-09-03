# -*- coding: utf-8 -*-
"""Web Push (VAPID) — notifications to iPhone/iPad (mirrored to Apple Watch), Android, desktop."""
import json
import asyncio
from .config import DATA_DIR
from . import memory

VAPID_FILE = DATA_DIR / "vapid.json"


def vapid_keys() -> dict:
    if VAPID_FILE.exists():
        return json.loads(VAPID_FILE.read_text(encoding="utf-8"))
    try:
        from py_vapid import Vapid
        import base64
        v = Vapid()
        v.generate_keys()
        from cryptography.hazmat.primitives import serialization
        priv = v.private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        raw_pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        pub = base64.urlsafe_b64encode(raw_pub).decode().rstrip("=")
        keys = {"public": pub, "private_pem": priv}
        VAPID_FILE.write_text(json.dumps(keys), encoding="utf-8")
        return keys
    except Exception as e:
        return {"public": "", "private_pem": "", "error": str(e)}


def _send(sub: dict, payload: dict):
    from pywebpush import webpush, WebPushException
    keys = vapid_keys()
    try:
        webpush(subscription_info=sub, data=json.dumps(payload), vapid_private_key=keys["private_pem"],
                vapid_claims={"sub": "mailto:jarvis@localhost"})
        return True
    except WebPushException as e:
        if getattr(e, "response", None) is not None and e.response.status_code in (404, 410):
            memory.remove_push_sub(sub.get("endpoint"))
        return False
    except Exception:
        return False


async def notify_all(title: str, body: str, url: str = "/"):
    subs = memory.push_subs()
    if not subs:
        return 0
    payload = {"title": title, "body": body, "url": url}
    results = await asyncio.gather(*[asyncio.to_thread(_send, s, payload) for s in subs])
    return sum(1 for r in results if r)
