import os
import json
import requests
from services.message_handler import handle_message
from services.allowlist_service import is_allowed, notify_admins_of_request, handle_admin_command
from utils.flex_message_builder import build_payload, send_already_bound_msg, save_user_id
from services.session_manager import load_session, save_session
from config.config import Config
import logging
from linebot import LineBotApi

logging.basicConfig(filename="error.log", level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")
line_bot_api = LineBotApi(Config.LINE_CHANNEL_ACCESS_TOKEN)

def handle_webhook(data, token):
    session = requests.session()
    session_data = {}
    if "events" not in data or not data["events"]:
        logging.warning("Webhook 事件為空，略過處理")
        return {"status": "no events"}

    event = data["events"][0]
    reply_token = event["replyToken"]
    uid = event["source"]["userId"]
    message_text = event.get("message", {}).get("text", "")

    session_data = load_session(uid)
    # 白名單（allowed_line_users）取代原本的帳號註冊 + 綁定；webhook 已驗證簽章，uid 可信
    allowed = is_allowed(uid)
    if allowed:
        save_user_id(uid)  # 只有白名單成員才列入每週提醒的收件人

    if event["type"] == "follow":
        if allowed:
            send_already_bound_msg(reply_token)
        else:
            notify_admins_of_request(uid)
            reply_simple(reply_token, "👋 已收到你的使用申請，管理員開通後就會通知你")
        return {"status": "follow handled"}

    elif event["type"] == "message":
        admin_reply = handle_admin_command(uid, message_text) if allowed else None
        if admin_reply is not None:
            payload = build_payload(reply_token, admin_reply)
        elif allowed:
            reply_text = handle_message(uid, message_text, session, session_data, token)
            payload = build_payload(reply_token, reply_text)
        else:
            # 舊的「綁定」流程已停用；任何訊息都視為申請並通知管理員
            notify_admins_of_request(uid)
            payload = {
                "replyToken": reply_token,
                "messages": [{"type": "text", "text": "⏳ 你還沒有使用權限，已通知管理員開通"}]
            }

        r = requests.post(Config.LINE_REPLY_URL, json=payload, headers=Config.headers)
        r.raise_for_status()

        save_session(uid, session_data)

        return {"status": "success"}

    return {"status": "ignored"}


def reply_simple(reply_token, text):
    r = requests.post(Config.LINE_REPLY_URL, headers=Config.headers,
                      json={"replyToken": reply_token, "messages": [{"type": "text", "text": text}]})
    if r.status_code != 200:
        logging.error(f"reply 失敗：{r.status_code} {r.text}")
