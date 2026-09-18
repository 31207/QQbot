import json
import os
import time

from radio.services.permissions import Permissions


def test_load_and_reload(tmp_path):
    path = tmp_path / "permissions.json"
    path.write_text(
        json.dumps({"admins": ["10001"], "super_admins": ["20002"]}), encoding="utf-8"
    )
    perms = Permissions(path)
    assert perms.is_admin("10001")
    assert perms.is_super_admin("20002")
    assert not perms.is_super_admin("10001")

    # 修改文件后按 mtime 自动重载（先写后改 mtime，避免时间戳粒度问题）
    path.write_text(
        json.dumps({"admins": ["30003"], "super_admins": []}), encoding="utf-8"
    )
    future = time.time() + 10
    os.utime(path, (future, future))
    assert perms.is_admin("30003")
    assert not perms.is_admin("10001")
    assert not perms.is_super_admin("20002")


def test_missing_file_is_empty(tmp_path):
    perms = Permissions(tmp_path / "nope.json")
    assert not perms.is_admin("10001")
    assert not perms.is_super_admin("10001")


def test_corrupt_file_falls_back(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    perms = Permissions(path)
    assert not perms.is_admin("10001")
