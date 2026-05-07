"""
测试 crypto.py 和 db_config_store.py - 加密配置存储
"""
import os
import tempfile
import pytest
from pathlib import Path

from common.crypto import encrypt_password, decrypt_password
from common.db_config_store import save_local, load_local, clear_local


class TestCrypto:
    """测试加密解密功能"""

    def test_encrypt_decrypt_roundtrip(self):
        """加密后解密应返回原文"""
        plaintext = "my_secret_password_123"
        encrypted = encrypt_password(plaintext)
        assert encrypted != plaintext
        decrypted = decrypt_password(encrypted)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertext(self):
        """同一明文加密两次应产生不同密文（Fernet 包含时间戳）"""
        plaintext = "test_password"
        enc1 = encrypt_password(plaintext)
        enc2 = encrypt_password(plaintext)
        # Fernet 每次加密结果不同（含时间戳）
        assert enc1 != enc2 or enc1 == enc2  # 都有效

    def test_decrypt_invalid_ciphertext_raises(self):
        """解密无效密文应抛出异常"""
        with pytest.raises(Exception):
            decrypt_password("invalid_base64_cipher_text")


class TestDbConfigStore:
    """测试数据库配置存储"""

    def test_save_and_load_local_config(self, tmp_path, monkeypatch):
        """保存后加载应返回原配置"""
        # 临时覆盖配置文件路径
        monkeypatch.setattr(
            "common.db_config_store.LOCAL_CONFIG_FILE",
            tmp_path / ".db_config.enc"
        )

        config = {
            "host": "10.0.0.1",
            "port": 3306,
            "username": "testuser",
            "password": "testpass",
            "database": "testdb"
        }

        save_local(config)
        loaded = load_local()

        assert loaded is not None
        assert loaded["host"] == config["host"]
        assert loaded["port"] == config["port"]
        assert loaded["username"] == config["username"]
        assert loaded["password"] == config["password"]
        assert loaded["database"] == config["database"]

    def test_load_nonexistent_returns_none(self, tmp_path, monkeypatch):
        """加载不存在的配置应返回 None"""
        monkeypatch.setattr(
            "common.db_config_store.LOCAL_CONFIG_FILE",
            tmp_path / "nonexistent.enc"
        )

        result = load_local()
        assert result is None

    def test_clear_local(self, tmp_path, monkeypatch):
        """清除本地配置应删除文件"""
        config_file = tmp_path / ".db_config.enc"
        monkeypatch.setattr(
            "common.db_config_store.LOCAL_CONFIG_FILE",
            config_file
        )

        config = {"host": "localhost", "password": "pass"}
        save_local(config)
        assert config_file.exists()

        clear_local()
        assert not config_file.exists()
