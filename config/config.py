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
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}"
    }
