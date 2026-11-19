# gunicorn 設定（k8s 用：`gunicorn -c gunicorn.conf.py app:app`）
# 一定要單一 worker：對話狀態（user_states）與 session token（user_sessions）都在 process 記憶體內。
# 注意：用 gunicorn 啟動時不會執行 app.py 的 create_rich_menu()；rich menu 存在 LINE 端，要重建時手動執行：
#   python -c "from utils.get_menu_items import create_rich_menu; create_rich_menu()"
import logging
import os
import sys

bind = f"0.0.0.0:{os.getenv('PORT', '5001')}"
workers = 1
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "8"))
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
accesslog = "-"
errorlog = "-"
# 只記 path、不記 query string（photo-syncer 回呼時帶 token）
access_log_format = '%(h)s %(t)s "%(m)s %(U)s" %(s)s %(b)s %(L)ss "%(a)s"'

# 在 app import 前把 root logger 指到 stdout；各模組的 basicConfig(filename="error.log") 因此不會生效
logging.basicConfig(stream=sys.stdout, level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
