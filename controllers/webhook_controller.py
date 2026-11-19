from flask import Blueprint, request, jsonify
import logging
from services.webhook_service import handle_webhook
from utils.session_utils import generate_token, user_sessions
import traceback
from config.config import Config
from utils.line_signature import is_valid_signature

webhook_bp = Blueprint("webhook_bp", __name__)
logging.basicConfig(filename="error.log", level=logging.ERROR, format="%(asctime)s - %(levelname)s - %(message)s")

@webhook_bp.route("/webhook", methods=["POST"])
def webhook():
    # 先驗證簽章（必須用原始 body），通過才處理；否則任何人都能偽造成任一 LINE 使用者
    body = request.get_data()
    signature = request.headers.get("X-Line-Signature", "")
    if not Config.LINE_CHANNEL_SECRET:
        logging.error("LINE_CHANNEL_SECRET 未設定，拒絕所有 webhook")
        return jsonify({"error": "server not configured"}), 500
    if not is_valid_signature(Config.LINE_CHANNEL_SECRET, body, signature):
        logging.error(f"webhook 簽章驗證失敗（來源 {request.headers.get('X-Real-IP') or request.remote_addr}）")
        return jsonify({"error": "invalid signature"}), 403

    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400
        # LINE Console 的「Verify」會送 events 為空的請求，回 200 即可
        if not data.get("events"):
            return jsonify({"status": "no events"}), 200
        uid = data["events"][0]["source"]["userId"]
        token = generate_token()
        if uid:
            user_sessions[token] = uid
        result = handle_webhook(data, token)
        return jsonify(result), 200
    except Exception as e:
        logging.error(f"Error in /webhook: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
