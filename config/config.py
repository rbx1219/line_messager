import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    # 用來驗證 webhook 的 X-Line-Signature（LINE Developers Console → Basic settings → Channel secret）
    LINE_CHANNEL_SECRET = (os.getenv("LINE_CHANNEL_SECRET") or "").strip()
    LINE_PUSH_URL = os.getenv("LINE_PUSH_URL")
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
    LINE_REPLY_URL=os.getenv("LINE_REPLY_URL")
    SERVER_URL=os.getenv("SERVER_URL")
    # photo-syncer API 的 base URL；k8s 內用 http://photo-syncer-svc:5050，預設走公開網址（NAS 時代的行為）
    PHOTO_API_URL = (os.getenv("PHOTO_API_URL") or f"{SERVER_URL}/api/upload").rstrip("/")
    # 每週提醒的收件人清單（k8s 內放在 PVC）
    USER_IDS_FILE = os.getenv("USER_IDS_FILE", "user_ids.txt")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
