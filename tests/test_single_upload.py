from unittest.mock import MagicMock, patch

import services.message_handler as mh
import services.request_service as rs

UID = "U" + "b" * 32


def setup_function():
    mh.user_states.clear()


def test_selecting_another_person_replaces_previous():
    mh.user_states[UID] = {"step": "ask_person", "faces": [{"ID": 19365, "name": "米"}, {"ID": 13437, "name": "暖"}],
                           "selected_person_id": []}
    mh.handle_message(UID, "SELECT_PERSON_19365", None, {}, "t")
    reply = mh.handle_message(UID, "SELECT_PERSON_13437", None, {}, "t")
    assert mh.user_states[UID]["selected_person_id"] == ["13437"]
    assert "暖" in str(reply)


def test_finish_selection_uploads_exactly_once():
    mh.user_states[UID] = {"step": "ask_person", "selected_person_id": ["19365"], "album_name": "", "num_photos": 5}
    with patch.object(mh, "upload_photos") as up:
        mh.handle_message(UID, "完成選擇", None, {}, "t")
    assert up.call_count == 1 and up.call_args.args[0] == "19365"


def test_409_from_photo_syncer_is_shown_as_busy_message():
    busy = MagicMock(status_code=409); busy.json.return_value = {"error": "相簿「Google Nest Hub」正在上傳中，請等上一批完成"}
    session = MagicMock(); session.post.return_value = busy; session.get.return_value = MagicMock(status_code=200)
    states = {UID: {"step": "uploading"}}
    with patch.object(rs, "line_bot_api") as api, patch("builtins.open", MagicMock()):
        rs.do_upload("19365", "Google Nest Hub", 200, UID, session, {}, states, "t")
    text = api.push_message.call_args.args[1].text
    assert text.startswith("⚠️") and "正在上傳中" in text
    assert session.post.call_count == 1          # 不重試
    assert states[UID]["step"] is None            # 狀態有清掉
