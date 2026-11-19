from unittest.mock import patch

import services.message_handler as mh

UID = "U" + "a" * 32


def _send(text):
    with patch.object(mh, "upload_photos", return_value="✅ 正在上傳") as up:
        reply = mh.handle_message(UID, text, session=None, session_data={}, token="t")
    return reply, up


def setup_function():
    mh.user_states.clear()


def test_quick_upload_starts_upload_with_preset():
    reply, up = _send("一鍵上傳 19365 200 Google Nest Hub")
    assert reply == "✅ 正在上傳"
    pid, state = up.call_args.args[0], up.call_args.args[1]
    assert pid == "19365"
    assert state["album_name"] == "Google Nest Hub" and state["num_photos"] == 200
    assert state["start_time"] is None and state["end_time"] is None
    assert state["is_uploading"] is True


def test_quick_upload_works_from_any_step():
    mh.user_states[UID] = {"step": "ask_count", "selected_person_id": ["1"]}
    reply, up = _send("一鍵上傳 13437 50 天穗")
    assert up.called and up.call_args.args[0] == "13437"


def test_rejects_bad_count_and_double_tap():
    reply, up = _send("一鍵上傳 19365 0 Google Nest Hub")
    assert "1～500" in reply and not up.called
    reply, up = _send("一鍵上傳 19365 9999 Google Nest Hub")
    assert "1～500" in reply and not up.called
    mh.user_states[UID] = {"step": None, "is_uploading": True}
    reply, up = _send("一鍵上傳 19365 200 Google Nest Hub")
    assert "上傳中" in reply and not up.called


def test_non_matching_text_is_not_quick_upload():
    assert mh.QUICK_UPLOAD_RE.match("一鍵上傳 abc 200 x") is None
    assert mh.QUICK_UPLOAD_RE.match("一鍵上傳 19365 200") is None
