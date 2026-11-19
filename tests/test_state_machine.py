"""docs/state-machine.md 已知問題 1、2、4 的回歸測試。"""
from unittest.mock import patch

import controllers.album_controller as ac
import services.message_handler as mh

UID = "U" + "c" * 32


def setup_function():
    mh.user_states.clear()


def _send(text):
    with patch.object(mh, "upload_photos", return_value="✅ 正在上傳") as up:
        reply = mh.handle_message(UID, text, None, {}, "t")
    return reply, up


# 1. 張數輸入錯誤時要停在 ask_count，可以重填
def test_bad_count_keeps_ask_count_then_valid_count_uploads():
    mh.user_states[UID] = {"step": "ask_count", "selected_person_id": ["19365"], "album_name": "A"}
    reply, up = _send("abc")
    assert not up.called and mh.user_states[UID]["step"] == "ask_count"
    assert "1～500" in str(reply)
    reply, up = _send("0")
    assert not up.called and mh.user_states[UID]["step"] == "ask_count"

    reply, up = _send("50")
    assert up.call_count == 1 and up.call_args.args[0] == "19365"
    state = mh.user_states[UID]
    assert state["step"] == "uploading" and state["is_uploading"] is True and state["num_photos"] == 50


# 2. 「完成選擇」直接上傳也要標記 is_uploading，連點只上傳一次
def test_finish_selection_double_tap_uploads_once():
    mh.user_states[UID] = {"step": "ask_person", "selected_person_id": ["19365"], "album_name": "", "num_photos": 5}
    _, up1 = _send("完成選擇")
    assert up1.call_count == 1 and mh.user_states[UID]["is_uploading"] is True
    # 第二次點：step 已是 uploading，不會再進 handle_person_selection；就算回到 ask_person 也會被擋
    mh.user_states[UID]["step"] = "ask_person"
    reply, up2 = _send("完成選擇")
    assert not up2.called and "上傳中" in str(reply)


def test_count_input_without_person_does_not_get_stuck():
    mh.user_states[UID] = {"step": "ask_count", "selected_person_id": [], "album_name": "A"}
    reply, up = _send("5")
    assert not up.called and "還沒有選擇人物" in str(reply)
    assert mh.user_states[UID]["step"] != "uploading"
    assert mh.user_states[UID]["is_uploading"] is False


# 4. 「列出我的相簿」回呼不能把還沒選人的使用者推進到 ask_google_album_name
def _post_album():
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(ac.album_bp)
    with patch.object(ac, "user_sessions", {"tok": UID}), patch.object(ac, "line_bot_api"), \
            patch.object(ac, "send_flex_album", return_value=None):
        return app.test_client().post("/album", json={"token": "tok", "album_titles": ["A"], "covers": ["c"]})


def _album_callback(step, **extra):
    mh.user_states[UID] = {"step": step, **extra}
    assert _post_album().status_code == 200
    return mh.user_states[UID]


def test_album_callback_leaves_unrelated_step_alone():
    assert _album_callback(None)["step"] is None
    assert _album_callback("ask_person")["step"] == "ask_person"
    assert _album_callback("ask_google_album_name")["step"] == "ask_google_album_name"


def test_album_callback_from_ask_count_goes_back_to_album_name():
    state = _album_callback("ask_count", history=["ask_person", "ask_google_album_name"])
    assert state["step"] == "ask_google_album_name"
    assert state["history"] == ["ask_person"]


def test_album_callback_for_unknown_user_does_not_crash():
    mh.user_states.clear()
    assert _post_album().status_code == 200
