"""
加密工具模块 - 使用 Fernet 对称加密保护敏感配置
密钥来源（按优先级）：
  1. 环境变量 ENCRYPTION_KEY（用于跨机器共享）
  2. 机器级密钥文件（自动生成，首次使用创建）
"""
import os
import logging
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

KEY_FILE = Path(__file__).resolve().parent.parent / ".encryption_key"
ENV_KEY_VAR = "ENCRYPTION_KEY"


def _get_or_create_key() -> bytes:
    """获取加密密钥（自动生成并缓存）"""
    env_key = os.getenv(ENV_KEY_VAR)
    if env_key:
        try:
            return env_key.encode() if isinstance(env_key, str) else env_key
        except Exception:
            logger.warning("ENCRYPTION_KEY 格式错误，回退到密钥文件")

    if KEY_FILE.exists():
        key_data = KEY_FILE.read_bytes().strip()
        if len(key_data) > 0:
            return key_data

    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    logger.info("已生成加密密钥文件: %s", KEY_FILE)
    return key


def encrypt_password(plaintext: str) -> str:
    """加密密码，返回 base64 字符串"""
    key = _get_or_create_key()
    f = Fernet(key)
    return f.encrypt(plaintext.encode()).decode()


def decrypt_password(ciphertext: str) -> str:
    """解密密码，返回明文"""
    key = _get_or_create_key()
    f = Fernet(key)
    return f.decrypt(ciphertext.encode()).decode()
