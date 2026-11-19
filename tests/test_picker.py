from unittest.mock import MagicMock, patch

import services.picker_service as ps

MEDIA = "A" * 100  # Google media item id 約 100 字元


def _page(total=25, offset=0, n=10):
    return {"total": total, "offset": offset, "items": [
        {"media_id": f"{MEDIA}{i}", "filename": f"IMG_{i}.JPG", "thumb_url": f"https://lh3.googleusercontent.com/x{i}=w600-h600-c",
         "photo_id": i, "time": "2026-11-19T07:52:19Z"} for i in range(offset, min(offset + n, total))]}


def _resp(json_data, status=200):
    r = MagicMock(status_code=status); r.json.return_value = json_data; r.raise_for_status.return_value = None
    return r


def test_parse_command():
    assert ps.parse_command("挑照片") == "Google Nest Hub"
    assert ps.parse_command("挑照片 天穗") == "天穗"
    assert ps.parse_command("我要上傳照片") is None


def test_first_page_has_10_bubbles_and_next_button():
    with patch.object(ps.requests, "get", return_value=_resp(_page())):
        msg = ps.build_page("Google Nest Hub", 0)
    d = msg.as_json_dict()
    bubbles = d["contents"]["contents"]
    assert len(bubbles) == 10
    data = bubbles[0]["footer"]["contents"][0]["action"]["data"]
    assert data == f"picker:exclude:Google Nest Hub|{MEDIA}0" and len(data) <= 300  # LINE postback data 上限 300
    labels = [it["action"]["label"] for it in d["quickReply"]["items"]]
    assert labels == ["下一頁（11～20）"]


def test_middle_page_has_prev_and_next():
    with patch.object(ps.requests, "get", return_value=_resp(_page(offset=10))):
        d = ps.handle_postback("picker:page:Google Nest Hub|10").as_json_dict()
    assert [it["action"]["label"] for it in d["quickReply"]["items"]] == ["下一頁（21～25）", "上一頁"]


def test_exclude_calls_photo_syncer():
    with patch.object(ps.requests, "post", return_value=_resp({"blacklisted": True, "filename": "IMG_3.JPG"})) as post:
        reply = ps.handle_postback(f"picker:exclude:天穗|{MEDIA}3")
    assert "以後不會再選到" in reply
    assert post.call_args.kwargs["json"] == {"album": "天穗", "media_id": f"{MEDIA}3"}


def test_non_picker_postback_ignored_and_errors_are_friendly():
    assert ps.handle_postback("something:else") is None
    with patch.object(ps.requests, "post", side_effect=RuntimeError("boom")):
        assert "失敗" in ps.handle_postback(f"picker:exclude:x|{MEDIA}")
