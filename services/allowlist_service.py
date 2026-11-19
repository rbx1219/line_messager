"""白名單：判斷誰能用 bot、通知管理員有新申請、處理管理員指令。

管理員指令（只有 is_admin 的人能用）：
  開通 <LINE ID> [名稱]          加入白名單（完整 ID 來自申請通知）
  停用 <編號|名稱|LINE ID>       移出白名單（不能停用管理員）
  名單                           列出白名單（只顯示部分 ID）
"""
import logging
import re

from linebot import LineBotApi
from linebot.models import TextSendMessage

from config.config import Config
from models.allowed_line_user import AllowedLineUser
from models.database import db

line_bot_api = LineBotApi(Config.LINE_CHANNEL_ACCESS_TOKEN)
LINE_ID_RE = re.compile(r"^U[0-9a-f]{32}$")


def get_user(line_id):
    return db.session.get(AllowedLineUser, line_id)


def mask_id(line_id):
    return f"{line_id[:4]}…{line_id[-3:]}" if len(line_id) > 8 else line_id


def ordered_users():
    return AllowedLineUser.query.order_by(AllowedLineUser.created_at, AllowedLineUser.line_id).all()


def resolve_target(ref):
    """「名單」的編號、名稱或完整 LINE ID → (user, 錯誤訊息)。"""
    users = ordered_users()
    if ref.isdigit():
        i = int(ref)
        return (users[i - 1], None) if 1 <= i <= len(users) else (None, f"⚠️ 沒有編號 {i}，請先傳「名單」確認")
    if LINE_ID_RE.match(ref):
        return (get_user(ref), None if get_user(ref) else "⚠️ 這個 ID 不在白名單裡")
    matches = [u for u in users if u.name == ref]
    if len(matches) == 1:
        return matches[0], None
    if not matches:
        return None, f"⚠️ 白名單裡沒有「{ref}」"
    return None, f"⚠️ 有 {len(matches)} 位叫「{ref}」，請改用編號"


def is_allowed(line_id):
    return get_user(line_id) is not None


def display_name(line_id):
    try:
        return line_bot_api.get_profile(line_id).display_name
    except Exception as e:
        logging.error(f"取得 LINE profile 失敗：{e}")
        return ""


def notify_admins_of_request(line_id):
    """有不在白名單的人加好友或傳訊息時，推播給所有管理員（附上可直接複製的開通指令）。"""
    name = display_name(line_id) or "（未知）"
    text = (f"🙋 有新使用者想使用相簿 bot\n名稱：{name}\nID：{line_id}\n\n"
            f"開通請回覆：\n開通 {line_id} {name}")
    for admin in AllowedLineUser.query.filter_by(is_admin=True).all():
        try:
            line_bot_api.push_message(admin.line_id, TextSendMessage(text=text))
        except Exception as e:
            logging.error(f"通知管理員失敗：{e}")


def handle_admin_command(sender_id, text):
    """回傳要回覆的文字；不是管理員指令時回傳 None（交給一般流程）。"""
    parts = text.strip().split(maxsplit=2)
    if not parts or parts[0] not in ("開通", "停用", "名單"):
        return None
    sender = get_user(sender_id)
    if not sender or not sender.is_admin:
        return None  # 非管理員：當一般訊息處理，不洩漏有這些指令

    cmd = parts[0]
    if cmd == "名單":
        users = ordered_users()
        lines = [f"{'👑' if u.is_admin else '👤'} {i}. {u.name or '（未命名）'}（{mask_id(u.line_id)}）"
                 for i, u in enumerate(users, 1)]
        return f"白名單（{len(users)} 人）\n" + "\n".join(lines) + "\n\n停用：停用 <編號或名稱>"

    if cmd == "停用":
        if len(parts) < 2:
            return "格式：停用 <編號|名稱|LINE ID>"
        target, err = resolve_target(" ".join(parts[1:]))
        if err:
            return err
        if target.is_admin:
            return "⚠️ 不能停用管理員"
        name = target.name or mask_id(target.line_id)
        db.session.delete(target)
        db.session.commit()
        return f"🚫 已停用 {name}"

    # 開通：需要完整 LINE ID（來自申請通知）
    if len(parts) < 2 or not LINE_ID_RE.match(parts[1]):
        return "格式：開通 <LINE ID> [名稱]（完整 ID 在申請通知裡）"
    target_id = parts[1]
    target = get_user(target_id)

    if cmd == "開通":
        name = parts[2] if len(parts) > 2 else display_name(target_id)
        if target:
            return f"✅ {target.name or target_id} 已經在白名單裡"
        db.session.add(AllowedLineUser(line_id=target_id, name=name or "", is_admin=False))
        db.session.commit()
        try:
            line_bot_api.push_message(target_id, TextSendMessage(text="🎉 你已經可以使用相簿 bot 了，請從選單選擇「我要上傳照片」開始"))
        except Exception as e:
            logging.error(f"通知新使用者失敗：{e}")
        return f"✅ 已開通 {name or target_id}"
