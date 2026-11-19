import time
import json
from config.config import Config
import logging
from linebot import LineBotApi
from linebot.models import TextSendMessage
import requests

logging.basicConfig(filename="error.log", level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")
line_bot_api = LineBotApi(Config.LINE_CHANNEL_ACCESS_TOKEN)

def do_upload(person_id, album_name, num_photos, user_id, session, session_data, user_states, token, start_time=None, end_time=None):
    success = False
    try:
        payload = {
            "personID": person_id,
            "albumName": album_name,
            "numPhotos": num_photos,
            "token": token,
            "start_time": start_time,
            "end_time": end_time
        }
        # token 不進 log（gunicorn access log 也刻意不記 query string）
        logging.info(f"開始上傳照片，payload: { {k: v for k, v in payload.items() if k != 'token'} }")

        for _ in range(5):
            response = session.post(f"{Config.PHOTO_API_URL}/upload_photos", params={"token": token}, json=payload)
            response2 = session.get(f"{Config.PHOTO_API_URL}/upload_records", params={"personID": person_id}, verify=False)

            if response.status_code == 409:
                # photo-syncer：同一本相簿已有上傳在進行（每次上傳會先清空相簿，不能同時跑兩個）
                try:
                    msg = response.json().get("error") or "相簿正在上傳中"
                except ValueError:
                    msg = "相簿正在上傳中"
                line_bot_api.push_message(user_id, TextSendMessage(text=f"⚠️ {msg}"))
                break
            if response.status_code != 200:
                logging.error(f"❌ sync_photos 回傳非 200：{response.status_code}, {response.text}")
                line_bot_api.push_message(user_id, TextSendMessage(text=f"❌ 同步失敗，請稍後再試。錯誤碼: {response.status_code}"))
                break

            # 嘗試解析 JSON
            try:
                data = response.json()
            except ValueError:
                logging.error("❌ sync_photos 回傳內容不是有效的 JSON")
                logging.error(f"回傳內容：{response.text}")
                line_bot_api.push_message(user_id, TextSendMessage(text=f"❌ 同步失敗，伺服器未回傳有效內容。"))
                break

            # 檢查 upload_records 成功與否
            if response2.status_code != 200:
                logging.error(f"❌ upload_records 失敗！Status: {response2.status_code}, Response: {response2.text}")
                break

            success = True
            line_bot_api.push_message(user_id, TextSendMessage(text=f"📄 同步報告：{data.get('message')}"))
            break

    except Exception as e:
        logging.error(f"❌ 其他錯誤: {e}")
    finally:
        if success:
            logging.error(f"✅ 狀態已成功清除")
        else:
            logging.warning(f"⚠️ 上傳失敗仍強制清除狀態")

        user_states[user_id] = {
            "step": None,
            "faces": [],
            "faces_loading": False,
            "selected_person_ids": [],
            "is_uploading": False,
        }
        session_data["last_action"] = None
        with open(f"sessions/{user_id}.json", "w") as f:
            json.dump(session_data, f)
        logging.error(f"🧹 強制清除狀態（無論成功或失敗）")

def notify_user(user_id, message):
    try:
        line_bot_api.push_message(user_id, TextSendMessage(text=message))
    except Exception as e:
        logging.error(f"推送訊息給 {user_id} 時失敗: {e}")

def request_interval_time_sync(session, user_id, person_id, token, start_time, end_time):
    try:
        payload = {
            "personID": person_id,
            "start_time": start_time,
            "end_time": end_time
        }
        url = f"{Config.PHOTO_API_URL}/sync_interval_time_photos"
        response = session.post(url, params={"token": token}, json=payload)
        if response.status_code != 200:
            logging.error(f"request_sync API failed: {response.status_code}, url={url}, body={response.text}")
            line_bot_api.push_message(user_id, TextSendMessage(
                text="⚠️ 同步照片時發生錯誤，請稍後再試。"
            ))
    except Exception as e:
        logging.error(f"未知的同步錯誤: {e}")

def request_sync(session, user_id, person_id, token, user_states):
    try:
        url = f"{Config.PHOTO_API_URL}/sync_latest_photo/{person_id}"
        response = session.get(url, params={"token": token})
        if response.status_code != 200:
            logging.error(f"request_sync API failed: {response.status_code}, url={url}, body={response.text}")
            line_bot_api.push_message(user_id, TextSendMessage(
                text="⚠️ 同步照片時發生錯誤，請稍後再試。"
            ))
    except Exception as e:
        logging.error(f"未知的同步錯誤: {e}")
    finally:
        user_states[user_id] = {
            "step": None,
            "faces": [],
            "selected_person_ids": [],
        }

def get_faces(session, user_id, user_states):
    try:
        logging.info(f"get_faces called for user {user_id}, current state: {user_states.get(user_id)}")

        response = session.get(f"{Config.PHOTO_API_URL}/update_people", params={"user_id": user_id})
        if response.status_code == 200:
            faces = response.json()

            state = user_states.setdefault(user_id, {})
            state["faces"] = faces
            state["faces_loading"] = False
        else:
            logging.error(f"取得人物列表失敗，狀態碼：{response.status_code}，內容：{response.text}")
            notify_user(user_id, f"❌ 取得人物列表失敗，狀態碼：{response.status_code}。")
            user_states.setdefault(user_id, {})["faces_loading"] = False
    except Exception as e:
        logging.error(f"取得人物列表時錯誤: {e}")
        notify_user(user_id, "❌ 取得人物列表時發生錯誤。")
        user_states.setdefault(user_id, {})["faces_loading"] = False

def get_album_list(token, user_id):
    try:
        response = requests.post(
            f"{Config.PHOTO_API_URL}/list_albums",
            params={"token": token},
            timeout=10
        )

        if response.status_code != 200:
            logging.error(f"list_albums API failed: {response.status_code}, {response.text}")
            line_bot_api.push_message(user_id, TextSendMessage(
                text="⚠️ 取得相簿時發生錯誤，請稍後再試。"
            ))
            return

        # 正常處理結果
        albums = response.json()
        # 可視需要推播訊息或更新狀態

    except requests.RequestException as e:
        logging.error(f"Failed to connect to album API: {e}")
        line_bot_api.push_message(user_id, TextSendMessage(
            text="⚠️ 無法連線至伺服器，請重新登入，稍後再試。"
        ))