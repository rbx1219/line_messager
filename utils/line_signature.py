"""驗證 LINE webhook 的 X-Line-Signature。

LINE 以 Channel Secret 對「原始 request body」做 HMAC-SHA256，再 base64 編碼放在 X-Line-Signature header。
沒有驗證的話，任何人都能偽造 webhook、冒充任一個 LINE 使用者（userId 寫在 body 裡）。
https://developers.line.biz/en/docs/messaging-api/receiving-messages/#verifying-signatures
"""
import base64
import hashlib
import hmac


def compute_signature(channel_secret: str, body: bytes) -> str:
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def is_valid_signature(channel_secret: str, body: bytes, signature: str) -> bool:
    """signature 為空、secret 未設定都視為無效（fail closed）。"""
    if not channel_secret or not signature:
        return False
    return hmac.compare_digest(compute_signature(channel_secret, body), signature)
