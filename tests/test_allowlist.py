from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from models.database import db
from models.allowed_line_user import AllowedLineUser
import services.allowlist_service as al

ADMIN = "U" + "a" * 32
MEMBER = "U" + "b" * 32
STRANGER = "U" + "c" * 32


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite://"
    db.init_app(app)
    with app.app_context():
        db.create_all()
        db.session.add_all([AllowedLineUser(line_id=ADMIN, name="管理員", is_admin=True),
                            AllowedLineUser(line_id=MEMBER, name="家人", is_admin=False)])
        db.session.commit()
        with patch.object(al, "line_bot_api", MagicMock()) as api:
            api.get_profile.return_value.display_name = "新朋友"
            yield app, api


def test_is_allowed(app):
    assert al.is_allowed(ADMIN) and al.is_allowed(MEMBER)
    assert not al.is_allowed(STRANGER)


def test_request_notifies_only_admins(app):
    _, api = app
    al.notify_admins_of_request(STRANGER)
    targets = [c.args[0] for c in api.push_message.call_args_list]
    assert targets == [ADMIN]
    assert STRANGER in api.push_message.call_args.args[1].text


def test_admin_can_enable_and_disable(app):
    _, api = app
    assert "已開通" in al.handle_admin_command(ADMIN, f"開通 {STRANGER} 小明")
    assert al.get_user(STRANGER).name == "小明"
    api.push_message.assert_called()  # 通知新使用者
    assert "已經在白名單" in al.handle_admin_command(ADMIN, f"開通 {STRANGER}")
    assert "已停用" in al.handle_admin_command(ADMIN, f"停用 {STRANGER}")
    assert not al.is_allowed(STRANGER)


def test_enable_without_name_uses_line_profile(app):
    al.handle_admin_command(ADMIN, f"開通 {STRANGER}")
    assert al.get_user(STRANGER).name == "新朋友"


def test_cannot_disable_admin(app):
    assert "不能停用管理員" in al.handle_admin_command(ADMIN, f"停用 {ADMIN}")
    assert al.is_allowed(ADMIN)


def test_non_admin_commands_fall_through(app):
    assert al.handle_admin_command(MEMBER, f"開通 {STRANGER}") is None
    assert not al.is_allowed(STRANGER)
    assert al.handle_admin_command(ADMIN, "我要上傳照片") is None


def test_list_masks_ids(app):
    out = al.handle_admin_command(ADMIN, "名單")
    assert "2 人" in out and "1. 管理員" in out and "2. 家人" in out
    assert MEMBER not in out and ADMIN not in out          # 不顯示完整 ID
    assert al.mask_id(MEMBER) in out
    assert "格式" in al.handle_admin_command(ADMIN, "開通 not-an-id")


def test_disable_by_number_name_or_id(app):
    for ref in ("2", "家人", MEMBER):
        al.handle_admin_command(ADMIN, f"開通 {MEMBER} 家人")  # 確保存在
        assert "已停用 家人" in al.handle_admin_command(ADMIN, f"停用 {ref}")
        assert not al.is_allowed(MEMBER)


def test_disable_errors(app):
    assert "沒有編號 9" in al.handle_admin_command(ADMIN, "停用 9")
    assert "沒有「路人」" in al.handle_admin_command(ADMIN, "停用 路人")
    assert "不能停用管理員" in al.handle_admin_command(ADMIN, "停用 1")
    al.handle_admin_command(ADMIN, f"開通 {STRANGER} 家人")
    assert "請改用編號" in al.handle_admin_command(ADMIN, "停用 家人")
