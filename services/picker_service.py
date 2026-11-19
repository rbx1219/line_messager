"""LINE 照片挑選器：「挑照片 [相簿名]」→ 以 carousel 顯示相簿目前的照片，每張可按「🚫 不要這張」。

按下後透過 photo-syncer 把照片移出相簿並加入黑名單（之後隨機挑選不會再選到）。
按鈕用 postback（data 不會出現在聊天室）：
  picker:exclude:<album>|<media_id>
  picker:page:<album>|<offset>
"""
import logging

import requests
from linebot.models import FlexSendMessage, PostbackAction, QuickReply, QuickReplyButton

from config.config import Config

DEFAULT_ALBUM = "Google Nest Hub"
PAGE_SIZE = 10
COMMAND = "挑照片"


def parse_command(text):
    """「挑照片」或「挑照片 天穗」→ 相簿名；不是這個指令回傳 None。"""
    text = (text or "").strip()
    if text == COMMAND:
        return DEFAULT_ALBUM
    if text.startswith(COMMAND + " "):
        return text[len(COMMAND):].strip() or DEFAULT_ALBUM
    return None


def _bubble(item, album):
    date = (item.get("time") or "")[:10]
    return {
        "type": "bubble",
        "size": "kilo",
        "hero": {"type": "image", "url": item["thumb_url"], "size": "full",
                 "aspectRatio": "1:1", "aspectMode": "cover"},
        "body": {"type": "box", "layout": "vertical", "paddingAll": "8px", "contents": [
            {"type": "text", "text": date or item.get("filename") or "", "size": "xs", "color": "#888888"},
        ]},
        "footer": {"type": "box", "layout": "vertical", "paddingAll": "8px", "contents": [
            {"type": "button", "style": "secondary", "height": "sm",
             "action": {"type": "postback", "label": "🚫 不要這張",
                        "data": f"picker:exclude:{album}|{item['media_id']}", "displayText": "🚫 不要這張"}},
        ]},
    }


def build_page(album, offset=0):
    r = requests.get(f"{Config.PHOTO_API_URL}/picker/photos",
                     params={"album": album, "offset": offset, "limit": PAGE_SIZE}, timeout=60)
    if r.status_code == 404:
        return f"⚠️ 找不到相簿「{album}」"
    r.raise_for_status()
    data = r.json()
    items, total = data["items"], data["total"]
    if not items:
        return f"📭 「{album}」沒有更多照片了（共 {total} 張）"

    end = offset + len(items)
    buttons = []
    if end < total:
        buttons.append(QuickReplyButton(action=PostbackAction(
            label=f"下一頁（{end + 1}～{min(end + PAGE_SIZE, total)}）", data=f"picker:page:{album}|{end}",
            display_text="下一頁")))
    if offset > 0:
        buttons.append(QuickReplyButton(action=PostbackAction(
            label="上一頁", data=f"picker:page:{album}|{max(offset - PAGE_SIZE, 0)}", display_text="上一頁")))
    return FlexSendMessage(
        alt_text=f"{album}：第 {offset + 1}～{end} 張（共 {total} 張）",
        contents={"type": "carousel", "contents": [_bubble(it, album) for it in items]},
        quick_reply=QuickReply(items=buttons) if buttons else None,
    )


def handle_postback(data):
    """回傳要回覆的訊息；不是 picker 的 postback 回傳 None。"""
    if not data.startswith("picker:"):
        return None
    kind, _, rest = data[len("picker:"):].partition(":")
    album, _, value = rest.rpartition("|")
    album = album or DEFAULT_ALBUM
    try:
        if kind == "page":
            return build_page(album, int(value or 0))
        if kind == "exclude":
            r = requests.post(f"{Config.PHOTO_API_URL}/picker/exclude",
                              json={"album": album, "media_id": value}, timeout=60)
            r.raise_for_status()
            res = r.json()
            if res.get("blacklisted"):
                return f"🚫 已從「{album}」移除 {res.get('filename')}，以後不會再選到這張"
            return f"🚫 已從「{album}」移除 {res.get('filename')}（找不到對應的 Synology 照片，未加入黑名單）"
    except Exception as e:
        logging.error(f"[picker] {kind} 失敗：{e}")
        return "⚠️ 處理失敗，請稍後再試"
    return None
