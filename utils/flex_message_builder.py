# utils/flex_message_builder.py
from linebot.models import FlexSendMessage
import requests
import os
from config.config import Config
import logging
logging.basicConfig(filename="error.log", level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {Config.LINE_CHANNEL_ACCESS_TOKEN}"
}

def build_payload(reply_token, reply_text):
    if isinstance(reply_text, FlexSendMessage):
        messages = [reply_text.as_json_dict()]
    elif isinstance(reply_text, dict) and "type" in reply_text:
        messages = [reply_text]
    elif isinstance(reply_text, list):
        messages = [
            msg.as_json_dict() if isinstance(msg, FlexSendMessage) else msg
            for msg in reply_text
        ]
    else:
        messages = [{"type": "text", "text": reply_text}]

    return {
        "replyToken": reply_token,
        "messages": messages
    }

def build_face_bubbles(faces):
    bubbles = []
    # bubbles.append(
    for face in faces:
        name = face["name"]
        img = face["img"]
        person_id = face['ID']
        bubble = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "lg",
                "contents": [
                    {
                        "type": "text",
                        "text": name,
                        "weight": "bold",
                        "size": "xl",
                        "align": "center"
                    },
                    {
                        "type": "image",
                        "url": img,
                        "aspectRatio": "1:1",
                        "size": "full",
                        "aspectMode": "cover",
                        "gravity": "center"
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "margin": "lg",
                        "action": {
                            "type": "message",
                            "label": "選擇",
                            "text": f"SELECT_PERSON_{person_id}"
                        }
                    }
                ]
            }
        }
        bubbles.append(bubble)
    carousel = {"type": "carousel", "contents": bubbles}
    return FlexSendMessage(alt_text="請選擇人物上傳", contents=carousel)

def send_bind_url(reply_token, uid):
    login_url = f"{Config.SERVER_URL}/Line-login?uid={uid}"
    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "text",
                "text": f"請點擊以下網址進行綁定：\n{login_url}"
            }
        ]
    }
    requests.post(Config.LINE_REPLY_URL, json=payload, headers=headers)

def get_album_name_input_options():
    return FlexSendMessage(
        alt_text="請選擇相簿名輸入方式",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "請選擇相簿名輸入方式：",
                        "wrap": True,
                        "weight": "bold",
                        "size": "md"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#1DB446",
                        "action": {
                            "type": "message",
                            "label": "🔘 從相簿列表選擇",
                            "text": "列出我的相簿"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "message",
                            "label": "📝 手動輸入相簿名",
                            "text": "手動輸入相簿名"
                        }
                    }
                ]
            }
        }
    )

def get_whether_interval_input_options():
    return FlexSendMessage(
        alt_text="請選擇是否指定照片時間",
        contents={
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    {
                        "type": "text",
                        "text": "是否選擇上傳時間間格",
                        "wrap": True,
                        "weight": "bold",
                        "size": "md"
                    }
                ]
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "button",
                        "style": "primary",
                        "color": "#1DB446",
                        "action": {
                            "type": "message",
                            "label": "🔘 預設隨機時間",
                            "text": "預設隨機時間"
                        }
                    },
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {
                            "type": "message",
                            "label": "📝 選擇時間間隔",
                            "text": "自訂同步相片間隔時間"
                        }
                    }
                ]
            }
        }
    )

def safe_url(url):
    if url and isinstance(url, str) and url.startswith("http"):
        return url
    return f"{Config.SERVER_URL}/images/grey.jpg"

def send_flex_album(album_titles, covers=None):
    bubbles = []
    logging.error(f"發送相簿列表：{album_titles}")
    album_titles = album_titles[:10]
    covers = covers[:10] if covers else []

    for i, album in enumerate(album_titles):
        logging.error(f"處理相簿：{album}")
        bubbles.append({
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "lg",
                "contents": [
                {
                    "type": "text",
                    "text": "🟡 請選擇相簿名稱",
                    "weight": "bold",
                    "size": "lg"
                },
                {
                    "type": "image",
                    "url": safe_url(covers[i] if covers and i < len(covers) else None),
                    "aspectRatio": "1:1",
                    "size": "full",
                    "aspectMode": "cover",
                    "gravity": "center"
                },
                {
                    "type": "text",
                    "text": album,
                    "weight": "bold",
                    "size": "lg",
                    "align": "center",
                    "gravity": "center"
                },
                {
                    "type": "button",
                    "style": "primary",
                    "action": {
                    "type": "message",
                    "label": "請選擇",
                    "text": album
                    }
                }
                ]
            }
            }
        )
    carousel = {"type": "carousel", "contents": bubbles}
    return FlexSendMessage(alt_text="請選擇相簿上傳", contents=carousel)

def save_user_id(uid, user_ids_file=None):
    user_ids_file = user_ids_file or Config.USER_IDS_FILE
    if os.path.exists(user_ids_file):
        with open(user_ids_file, 'r', encoding='utf-8') as f:
            existing_ids = set(line.strip() for line in f if line.strip())
    else:
        existing_ids = set()

    if uid not in existing_ids:
        with open(user_ids_file, 'a', encoding='utf-8') as f:
            f.write(uid + '\n')
        print(f"新增 user_id: {uid}")
    else:
        print(f"user_id {uid} 已存在，不重複寫入")
def send_already_bound_msg(reply_token):
    payload = {
        "replyToken": reply_token,
        "messages": [
            {"type": "text", "text": "您已經綁定過帳號，謝謝！"}
        ]
    }
    requests.post(Config.LINE_REPLY_URL, json=payload, headers=headers)

def send_bind_button(reply_token, uid):
    bind_url = f"{Config.SERVER_URL}/Line-login?uid={uid}"

    payload = {
        "replyToken": reply_token,
        "messages": [
            {
                "type": "template",
                "altText": "請點擊以下按鈕進行綁定",
                "template": {
                    "type": "buttons",
                    "title": "帳號綁定",
                    "text": "請點擊下方按鈕以綁定您的帳號",
                    "actions": [
                        {
                            "type": "uri",
                            "label": "前往綁定",
                            "uri": bind_url
                        }
                    ]
                }
            }
        ]
    }

    requests.post(Config.LINE_REPLY_URL, json=payload, headers=headers)