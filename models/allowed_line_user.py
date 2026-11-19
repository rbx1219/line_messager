from datetime import datetime

from models.database import db


class AllowedLineUser(db.Model):
    """可以使用 bot 的 LINE 使用者白名單（取代帳號註冊 + 綁定）。

    LINE webhook 已驗證簽章，event 裡的 userId 可信，所以只要判斷 userId 在不在名單內。
    """
    __tablename__ = "allowed_line_users"

    line_id = db.Column(db.String(64), primary_key=True)
    name = db.Column(db.String(100), nullable=False, default="")
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
