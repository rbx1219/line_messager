import re
import threading
from linebot.models import FlexSendMessage
from utils.flex_message_builder import build_face_bubbles, get_album_name_input_options, get_whether_interval_input_options
from services.request_service import do_upload, get_album_list, get_faces, request_sync, request_interval_time_sync
from config.config import Config
import logging
import requests
from dotenv import load_dotenv
from linebot import LineBotApi
from linebot.models import TextSendMessage, QuickReply, QuickReplyButton, MessageAction, BubbleContainer, CarouselContainer
from datetime import datetime

load_dotenv()

session = requests.Session()

logging.basicConfig(filename="error.log", level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")
line_bot_api = LineBotApi(Config.LINE_CHANNEL_ACCESS_TOKEN)

VALID_TRANSITIONS = {
    None: ["ask_person", "start", "ask_sync"],
    "ask_sync": ["ask_sync_person"],
    "ask_sync_person": ["sync_photo"],
    "sync_photo":[],
    "ask_person": ["ask_whether_interval", "ask_google_album_name", "uploading"],
    "ask_google_album_name": ["ask_count"],
    "ask_whether_interval":["ask_photo_start_time", "ask_google_album_name"],
    "ask_photo_start_time": ["ask_photo_end_time"],
    "ask_photo_end_time":["ask_google_album_name"],
    "ask_count": ["uploading"],
    "uploading": [],
}

def is_valid_transition(current_step, next_step):
    return next_step in VALID_TRANSITIONS.get(current_step, [])

def set_user_step(user_id, state, next_step, skip_validation=False):
    if state.get("step") == next_step:
        return True
    if not skip_validation and not is_valid_transition(state.get("step"), next_step):
        raise ValueError(f"非法狀態轉移：{state.get('step')} ➜ {next_step}")
    history = state.setdefault("history", [])
    if state.get("step"):
        history.append(state["step"])
    state["step"] = next_step
    user_states[user_id] = state

def go_back_step(user_id):
    state = user_states.get(user_id)
    history = state.get("history", [])

    if not history:
        user_states[user_id] = {
            "step": None,
            "faces": [],
            "faces_loading": False,
            "selected_person_id": [],
            "is_uploading": False,
        }
        return ["📸 已返回起始狀態，請於圖文選單選擇「我要上傳照片」來開始上傳流程"]

    previous_step = history.pop()
    state["step"] = previous_step
    user_states[user_id] = state

    if previous_step == "ask_person":
        state["selected_person_id"] = []
        return [TextSendMessage(
            text="📸 已返回人物選擇，請選擇下一步動作：",
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="我要上傳照片", text="我要上傳照片")),
                QuickReplyButton(action=MessageAction(label="不需要上傳", text="不需要上傳")),
                QuickReplyButton(action=MessageAction(label="使用自訂參數", text="使用自訂參數")),
            ])
        )]

    elif previous_step == "ask_whether_interval":
        return add_back_button_to_message(get_whether_interval_input_options())

    elif previous_step == "ask_photo_start_time":
        return add_back_button_to_message("請輸入同步起始時間，例如 2025年6月1日")

    elif previous_step == "ask_photo_end_time":
        return add_back_button_to_message("請輸入同步截止時間，例如 2025年7月1日")

    elif previous_step == "ask_google_album_name":
        return add_back_button_to_message(get_album_name_input_options())

    elif previous_step == "ask_count":
        return add_back_button_to_message(
            handle_album_name_input(user_id, state.get("album_name", ""), state)
        )

    return [TextSendMessage(text=f"↩️ 已退回到步驟：{previous_step}")]


def add_back_button_to_message(msg):
    back_button = {
        "type": "action",
        "action": {
            "type": "message",
            "label": "↩️ 返回上一步",
            "text": "返回上一步"
        }
    }

    def add_quick_reply_to_dict(message_dict):
        if "quickReply" not in message_dict:
            message_dict["quickReply"] = {"items": [back_button]}
        else:
            message_dict["quickReply"]["items"].append(back_button)
        return message_dict

    if hasattr(msg, "as_json_dict"):
        msg_dict = msg.as_json_dict()
        return [msg_dict,
                {
                    "type": "text",
                    "text": "↩️ 您可以點選下方按鈕返回上一步",
                    "quickReply": {"items": [back_button]}
                }]

    if isinstance(msg, list):
        result = []
        has_text = False
        for m in msg:
            if hasattr(m, "as_json_dict"):
                result.append(add_quick_reply_to_dict(m.as_json_dict()))
                has_text = True
            elif isinstance(m, dict):
                result.append(add_quick_reply_to_dict(m))
                has_text = True
            elif isinstance(m, str):
                result.append({
                    "type": "text",
                    "text": m,
                    "quickReply": {"items": [back_button]}
                })
                has_text = True
            else:
                raise TypeError(f"Unsupported message type in list: {type(m)}")

        if not has_text:
            result.append({
                "type": "text",
                "text": "↩️ 您可以點選下方按鈕返回上一步",
                "quickReply": {"items": [back_button]}
            })
        return result

    if isinstance(msg, str):
        return [{
            "type": "text",
            "text": msg,
            "quickReply": {"items": [back_button]}
        }]

    if isinstance(msg, dict):
        return [add_quick_reply_to_dict(msg)]

    raise TypeError(f"Unsupported message type: {type(msg)}")

user_states = {}

def handle_message(user_id, message_text, session, session_data, token):
    try:
        default_state = {
            "step": None,
            "faces": [],
            "faces_loading": False,
            "selected_person_id": [],
            "is_uploading": False,
            "start_time": None,
            "end_time":None,
        }

        state = user_states.setdefault(user_id, {})
        for key, value in default_state.items():
            state.setdefault(key, value)

        current_step = state.get("step")
        logging.error(f"current step: {current_step}")
        if current_step not in VALID_TRANSITIONS:
            return add_back_button_to_message(TextSendMessage(text="⚠️ 發生錯誤，請重新開始流程。"))

        if message_text == "返回上一步":
            return add_back_button_to_message(go_back_step(user_id))

        # 一鍵上傳（每週提醒的預設按鈕）：不管目前在哪一步都直接開始
        quick = QUICK_UPLOAD_RE.match(message_text.strip())
        if quick:
            return handle_quick_upload(user_id, state, quick, session, session_data, token)

        if message_text == "使用自訂參數":
            set_user_step(user_id, state, "ask_person", skip_validation=True)
            return handle_custom_parameters(user_id)

        elif message_text == "我要上傳照片":
            set_user_step(user_id, state, "ask_person", skip_validation=True)
            return handle_start_upload(user_id)

        elif message_text == "強制同步新照片":
            set_user_step(user_id, state, "ask_sync")
            return request_person_id(user_id)

        if message_text == "列出我的相簿":
            return handle_list_albums(user_id, token)

        elif message_text == "手動輸入相簿名":
            return add_back_button_to_message(TextSendMessage(text="🔤 請輸入相簿名稱："))

        if message_text == "自訂同步相片間隔時間":
            set_user_step(user_id, state, "ask_photo_start_time")
            return "請輸入同步照片**開始時間**，例如 2025年1月1日"

        elif message_text == "預設隨機時間":
            set_user_step(user_id, state, "ask_google_album_name")

        if current_step == "ask_photo_start_time":
            return save_start_time_and_ask_end_time(message_text, user_id)

        if current_step == "ask_photo_end_time":
            return save_end_time(message_text, user_id, token)

        if current_step == "ask_sync_person":
            return send_request(message_text, user_id, token)

        if current_step == "ask_person":
            return add_back_button_to_message(
                handle_person_selection(user_id, message_text, state, session, session_data, token)
            )

        if current_step == "ask_whether_interval":
            set_user_step(user_id, state, "ask_google_album_name")
            return add_back_button_to_message(get_album_name_input_options())

        if current_step == "ask_google_album_name":
            set_user_step(user_id, state, "ask_count")
            return add_back_button_to_message(handle_album_name_input(user_id, message_text, state))

        if current_step == "ask_count":
            set_user_step(user_id, state, "uploading")
            return add_back_button_to_message(handle_photo_count_input(
                user_id, message_text, state, session, session_data, token
            ))

        return add_back_button_to_message(TextSendMessage(
            text="請輸入「我要上傳照片」來開始相簿上傳流程。"
        ))

    except Exception as e:
        logging.error(e)
        return add_back_button_to_message(TextSendMessage(
            text="⚠️ 發生錯誤，請稍後再試。"
        ))

def select_person(user_id):
    state = user_states.get(user_id, {})
    faces = state.get("faces", [])
    faces_loading = state.get("faces_loading", False)

    if not faces:
        if not faces_loading:
            state.update({
                "faces_loading": True
            })
            threading.Thread(target=get_faces, args=(session, user_id, user_states)).start()
            user_states[user_id] = state
            logging.error(f"user_states:{user_states[user_id]}")
            return "⚠️ 正在取得人物列表，完成後會通知您。"
        else:
            return "⚠️ 人物列表仍在載入中，請稍候..."

    flex_msg = build_face_bubbles(faces)
    return flex_msg

def request_person_id(user_id):
    state = user_states.get(user_id, {})
    get_faces(session, user_id, user_states)
    set_user_step(user_id, state, "ask_sync_person")
    return "請先選擇人物"

def send_request(message_text, user_id, token):
    state = user_states.get(user_id, {})
    person_id = message_text.replace("SELECT_PERSON_", "")
    set_user_step(user_id, state, "sync_photo")
    threading.Thread(target=request_sync, args=(session, user_id, person_id, token, user_states)).start()
    return "已發送同步請求"

def get_sync_interval_time(user_id, token, start_time, end_time):
    state = user_states.get(user_id, {})
    person_id = state['selected_person_id'][0]
    start_time = state['start_time']
    end_time = state['end_time']
    set_user_step(user_id, state, "ask_google_album_name")
    threading.Thread(target=request_interval_time_sync, args=(session, user_id, person_id, token, start_time, end_time)).start()
    return "已發送同步請求"

def handle_list_albums(user_id, token):
    threading.Thread(target=get_album_list, args=(token, user_id)).start()
    return "📂 正在列出所有相簿，請稍候..."

# 格式：一鍵上傳 <personID> <張數> <相簿名>（相簿名可含空白），由 photo_syncer tools/line_reminder.py 的預設按鈕送出
QUICK_UPLOAD_RE = re.compile(r"^一鍵上傳\s+(\d+)\s+(\d+)\s+(.+)$")
QUICK_UPLOAD_MAX = 500


def handle_quick_upload(user_id, state, match, session, session_data, token):
    person_id, count, album = match.group(1), int(match.group(2)), match.group(3).strip()
    if not 1 <= count <= QUICK_UPLOAD_MAX:
        return f"❌ 張數需在 1～{QUICK_UPLOAD_MAX} 之間"
    if not album:
        return "❌ 請指定相簿名稱"
    if state.get("is_uploading"):
        return "⚠️ 照片正在上傳中，請稍候完成後再試一次。"
    state.update({
        "selected_person_id": [person_id],
        "album_name": album,
        "num_photos": count,
        "start_time": None,
        "end_time": None,
        "is_uploading": True,
    })
    set_user_step(user_id, state, "uploading", skip_validation=True)
    user_states[user_id] = state
    logging.info(f"一鍵上傳：person={person_id} count={count} album={album}")
    return upload_photos(person_id, state, user_id, session, session_data, token)


def handle_custom_parameters(user_id):
    try:
        select_person(user_id)
        flex_msg = select_person(user_id)

        return add_back_button_to_message(flex_msg)
    except Exception as e:
            logging.error(f"handle_custom_parameters 未知的錯誤:{e}")

def handle_start_upload(user_id):
    try:
        flex_msg = select_person(user_id)

        state = user_states.get(user_id, {})
        state.update({
            "step": "ask_person",
            "album_name": "",
            "num_photos": 5,
            "faces_loading": True
        })

        return add_back_button_to_message(flex_msg)
    except Exception as e:
        logging.error(f"handle_start_upload 未知的錯誤:{e}")

def extract_person_id_from_text_or_action(message_text, state):
    if message_text.startswith("SELECT_PERSON_"):
        return message_text.replace("SELECT_PERSON_", "")
    for face in state.get("faces", []):
        if face["name"] == message_text:
            return face["ID"]
    return None

def handle_person_selection(user_id, message_text, state, session, session_data, token):
    person_id = None
    try:
        if message_text.startswith("SELECT_PERSON_"):
            person_id = extract_person_id_from_text_or_action(message_text, state)
            if not person_id or not person_id.isdigit():
                return {
                    "type": "text",
                    "text": "❌ 請提供有效的人物 ID"
                }
            # 一次只上傳一位人物：多人會同時對同一本相簿上傳、互相清掉照片（photo-syncer 也會拒絕並發）
            state["selected_person_id"] = [person_id]
            name = next((f.get("name") for f in state.get("faces", []) if str(f.get("ID")) == person_id), None)

            selection_already = {
                "type": "action",
                "action": {
                    "type": "message",
                    "label": "✅ 完成選擇",
                    "text": "完成選擇"
                }
            }
            return {
                "type": "text",
                "text": f"✅ 已選擇{name or '人物'}。要換人直接點其他人的「選擇」，或按『完成選擇』繼續。",
                "quickReply": {
                    "items": [selection_already]
                }
            }

        elif message_text == "完成選擇":
            if not state["selected_person_id"]:
                return {
                    "type": "text",
                    "text": "⚠️ 請至少選擇一位人物再進行下一步。"
                }

            if "album_name" in state and "num_photos" in state:
                if state.get("is_uploading"):
                    return {
                        "type": "text",
                        "text": "⚠️ 照片正在上傳中，請稍候完成後再試一次。"
                    }

                state["step"] = "uploading"
                user_states[user_id] = state

                upload_photos(state["selected_person_id"][0], state, user_id, session, session_data, token)

                return {
                    "type": "text",
                    "text": "📤 照片上傳中，請稍候..."
                }
            else:
                set_user_step(user_id, state, "ask_whether_interval")
                return get_whether_interval_input_options()

        else:
            return {
                "type": "text",
                "text": "請點選選單上的「選擇」按鈕選擇人物，或輸入『完成選擇』繼續。"
            }
    except Exception as e:
        import traceback
        logging.error(f"handle_person_selection 未知的錯誤:\n{traceback.format_exc()}")
        return {
            "type": "text",
            "text": "❌ 發生錯誤，請稍後再試一次。"
        }

def handle_photo_count_input(user_id, message_text, state, session, session_data, token):
    try:
        if not message_text.isdigit():
            return "❌ 請輸入正確的數字"
        num_photos = int(message_text)
        person_id = state["selected_person_id"][0]

        if state["is_uploading"]:
            return "⚠️ 照片正在上傳中，請稍候完成後再試一次。"

        state["num_photos"] = num_photos
        state["is_uploading"] = True
        user_states[user_id] = state

        return upload_photos(person_id, state, user_id, session, session_data, token)
    except Exception as e:
        logging.error(f"handle_photo_count_input 未知的錯誤:{e}")
        return "⚠️ 發生錯誤，請稍後再試。"


def parse_date_string(date_str):
    try:
        clean = date_str.replace("年", "-").replace("月", "-").replace("日", "")
        dt = datetime.strptime(clean, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        raise ValueError("日期格式錯誤，請用 '2025年6月1日' 這種格式輸入")

def save_start_time_and_ask_end_time(message_text, user_id):
    try:
        state = user_states.get(user_id, {})
        date_str = parse_date_string(message_text)
        state["start_time"] = date_str
        user_states[user_id] = state
        set_user_step(user_id, state, "ask_photo_end_time")
        return "請輸入同步照片**截止時間**，例如 2025年7月1日"
    except ValueError as ve:
        return str(ve)
    except Exception as e:
        logging.error(f"未知錯誤 save_start_time: {e}")
        return "發生錯誤，請重新輸入起始時間"

def save_end_time(message_text, user_id, token):
    try:
        state = user_states.get(user_id, {})
        date_str = parse_date_string(message_text)
        state["end_time"] = date_str
        user_states[user_id] = state
        logging.info(f"{user_id} 設定結束時間為 {date_str}")

        get_sync_interval_time(user_id, token, state["start_time"], state["end_time"])
        set_user_step(user_id, state, "ask_google_album_name")
        return get_album_name_input_options()
    except ValueError as ve:
        return str(ve)
    except Exception as e:
        logging.error(f"未知錯誤 save_end_time: {e}")
        return "發生錯誤，請重新輸入截止時間"

def upload_photos(person_id, state, user_id, session, session_data, token):
    threading.Thread(
        target=do_upload,
        args=(person_id, state["album_name"], state['num_photos'],
                user_id, session, session_data, user_states, token, state.get("start_time"), state.get("end_time"))
    ).start()

    return f"✅ 正在上傳 {state['num_photos']} 張照片到相簿中，請稍候..."

def handle_album_name_input(user_id, message_text, state):
    try:
        state["album_name"] = message_text
        user_states[user_id] = state
        return {
            "type": "text",
            "text": "請選擇要上傳的照片張數：",
            "quickReply": {
                "items": [
                    {"type":"action","action":{"type":"message","label":"5 張","text":"5"}},
                    {"type":"action","action":{"type":"message","label":"50 張","text":"50"}},
                    {"type":"action","action":{"type":"message","label":"100 張","text":"100"}},
                    {"type":"action","action":{"type":"message","label":"200 張","text":"200"}}
                ]
            }
        }
    except Exception as e:
        logging.error(f"handle_album_name_input 未知的錯誤:{e}")