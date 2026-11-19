import json
import sys
import types
from unittest.mock import patch

import pytest
from flask import Flask

from utils.line_signature import compute_signature, is_valid_signature

SECRET = "test-channel-secret"


def test_valid_signature():
    body = b'{"events":[]}'
    assert is_valid_signature(SECRET, body, compute_signature(SECRET, body))


def test_tampered_body_is_rejected():
    sig = compute_signature(SECRET, b'{"events":[]}')
    assert not is_valid_signature(SECRET, b'{"events":[1]}', sig)


def test_missing_signature_or_secret_is_rejected():
    body = b"{}"
    assert not is_valid_signature(SECRET, body, "")
    assert not is_valid_signature("", body, compute_signature(SECRET, body))


@pytest.fixture
def client():
    # webhook_controller 會 import services.webhook_service（需要 DB），測試時換成假的
    fake_service = types.ModuleType("services.webhook_service")
    fake_service.handle_webhook = lambda data, token: {"status": "handled"}
    with patch.dict(sys.modules, {"services.webhook_service": fake_service}):
        sys.modules.pop("controllers.webhook_controller", None)
        from controllers import webhook_controller
        app = Flask(__name__)
        app.register_blueprint(webhook_controller.webhook_bp)
        with patch.object(webhook_controller.Config, "LINE_CHANNEL_SECRET", SECRET):
            yield app.test_client(), webhook_controller


def _event_body(uid="Uabc"):
    return json.dumps({"events": [{"type": "message", "replyToken": "r",
                                   "source": {"userId": uid}, "message": {"text": "hi"}}]}).encode()


def test_webhook_accepts_valid_signature(client):
    c, _ = client
    body = _event_body()
    r = c.post("/webhook", data=body, headers={"X-Line-Signature": compute_signature(SECRET, body),
                                               "Content-Type": "application/json"})
    assert r.status_code == 200 and r.get_json() == {"status": "handled"}


def test_webhook_rejects_forged_request(client):
    c, _ = client
    body = _event_body()
    r = c.post("/webhook", data=body, headers={"X-Line-Signature": compute_signature("wrong", body)})
    assert r.status_code == 403
    r = c.post("/webhook", data=body)  # 沒有簽章
    assert r.status_code == 403


def test_webhook_verify_request_with_no_events(client):
    c, _ = client
    body = b'{"destination":"x","events":[]}'
    r = c.post("/webhook", data=body, headers={"X-Line-Signature": compute_signature(SECRET, body)})
    assert r.status_code == 200


def test_webhook_fails_closed_without_secret(client):
    c, mod = client
    body = _event_body()
    with patch.object(mod.Config, "LINE_CHANNEL_SECRET", ""):
        r = c.post("/webhook", data=body, headers={"X-Line-Signature": compute_signature(SECRET, body)})
    assert r.status_code == 500


def test_get_is_not_allowed(client):
    c, _ = client
    assert c.get("/webhook").status_code == 405
