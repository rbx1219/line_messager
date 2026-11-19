from unittest.mock import MagicMock, patch

import services.picker_service as ps

MEDIA = "A" * 100  # Google media item id 約 100 字元


def _page(total=125, offset=0, n=50):
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


def test_first_page_is_5_carousels_of_10_with_next_on_last():
    with patch.object(ps.requests, "get", return_value=_resp(_page())):
        msgs = ps.build_page("Google Nest Hub", 0)
    ds = [m.as_json_dict() for m in msgs]
    assert len(ds) == 5 and all(len(d["contents"]["contents"]) == 10 for d in ds)   # LINE：一次最多 5 則
    data = ds[0]["contents"]["contents"][0]["footer"]["contents"][0]["action"]["data"]
    assert data == f"picker:exclude:Google Nest Hub|0|{MEDIA}0" and len(data) <= 300  # LINE postback data 上限 300
    assert all("quickReply" not in d for d in ds[:-1])
    assert [it["action"]["label"] for it in ds[-1]["quickReply"]["items"]] == ["下一頁（51～100）"]


def test_middle_page_has_prev_and_next():
    with patch.object(ps.requests, "get", return_value=_resp(_page(offset=50))):
        msgs = ps.handle_postback("picker:page:Google Nest Hub|50")
    d = msgs[-1].as_json_dict()
    assert [it["action"]["label"] for it in d["quickReply"]["items"]] == ["下一頁（101～125）", "上一頁"]


def test_exclude_calls_photo_syncer():
    with patch.object(ps.requests, "post", return_value=_resp({"blacklisted": True, "filename": "IMG_3.JPG"})) as post:
        reply = ps.handle_postback(f"picker:exclude:天穗|10|{MEDIA}3")
    assert "以後不會再選到" in reply["text"]
    assert post.call_args.kwargs["json"] == {"album": "天穗", "media_id": f"{MEDIA}3"}
    # 移除後仍可繼續操作：重新整理這一頁（offset 10）與下一頁（offset 20）
    datas = [it["action"]["data"] for it in reply["quickReply"]["items"]]
    assert datas == ["picker:page:天穗|10", "picker:page:天穗|60"]


def test_old_exclude_format_still_works():
    with patch.object(ps.requests, "post", return_value=_resp({"blacklisted": True, "filename": "a"})) as post:
        reply = ps.handle_postback(f"picker:exclude:Google Nest Hub|{MEDIA}")
    assert post.call_args.kwargs["json"]["media_id"] == MEDIA
    assert reply["quickReply"]["items"][1]["action"]["data"] == "picker:page:Google Nest Hub|50"


def test_non_picker_postback_ignored_and_errors_are_friendly():
    assert ps.handle_postback("something:else") is None
    with patch.object(ps.requests, "post", side_effect=RuntimeError("boom")):
        assert "失敗" in ps.handle_postback(f"picker:exclude:x|{MEDIA}")
