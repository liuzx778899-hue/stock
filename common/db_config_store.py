"""
数据库配置存储 - 两级存储（本地加密文件 + 数据库 system_config 表）

fallback 顺序：
  1. load_local()     -- 本地加密文件（快，无需 DB 连接）
  2. 环境变量 / .env   -- 向后兼容
  3. load_from_db()   -- 数据库 system_config 表
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from common.crypto import encrypt_password, decrypt_password

logger = logging.getLogger(__name__)

LOCAL_CONFIG_FILE = Path(__file__).resolve().parent.parent / ".db_config.enc"

KEY_DB_CONFIG = "database.connection"

DEFAULT_CONFIG = {
    "host": "192.168.2.32",
    "port": 2881,
    "username": "root@hdw",
    "database": "astock",
}


def save_local(config: Dict[str, Any]) -> None:
    """保存数据库配置到本地加密文件。密码以 Fernet 加密存储。"""
    record = {
        "host": config.get("host", DEFAULT_CONFIG["host"]),
        "port": config.get("port", DEFAULT_CONFIG["port"]),
        "username": config.get("username", DEFAULT_CONFIG["username"]),
        "database": config.get("database", DEFAULT_CONFIG["database"]),
        "updated_at": datetime.now().isoformat(),
    }
    raw_pw = config.get("password", "")
    if raw_pw:
        record["password_encrypted"] = encrypt_password(raw_pw)

    LOCAL_CONFIG_FILE.write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info("数据库配置已保存到本地加密文件: %s", LOCAL_CONFIG_FILE)


def load_local() -> Optional[Dict[str, Any]]:
    """从本地加密文件读取数据库配置。返回包含明文 password 的 dict，或 None。"""
    if not LOCAL_CONFIG_FILE.exists():
        return None

    try:
        data = json.loads(LOCAL_CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("本地加密配置文件损坏: %s", e)
        return None

    result = {
        "host": data.get("host", DEFAULT_CONFIG["host"]),
        "port": data.get("port", DEFAULT_CONFIG["port"]),
        "username": data.get("username", DEFAULT_CONFIG["username"]),
        "database": data.get("database", DEFAULT_CONFIG["database"]),
    }

    enc_pw = data.get("password_encrypted")
    if enc_pw:
        try:
            result["password"] = decrypt_password(enc_pw)
        except Exception as e:
            logger.warning("解密本地配置文件密码失败: %s", e)
            return None

    return result


def save_to_db(engine: Engine, config_dict: Dict[str, Any]) -> None:
    """将数据库配置保存到 system_config 表。密码以加密形式存储。"""
    enc_pw = encrypt_password(config_dict["password"])
    payload = {
        "host": config_dict.get("host", DEFAULT_CONFIG["host"]),
        "port": config_dict.get("port", DEFAULT_CONFIG["port"]),
        "username": config_dict.get("username", DEFAULT_CONFIG["username"]),
        "database": config_dict.get("database", DEFAULT_CONFIG["database"]),
        "password_encrypted": enc_pw,
        "updated_at": datetime.now().isoformat(),
    }

    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO system_config (config_key, config_value, updated_at)
                VALUES (:key, :value, NOW())
                ON DUPLICATE KEY UPDATE
                    config_value = VALUES(config_value),
                    updated_at = NOW()
            """),
            {"key": KEY_DB_CONFIG, "value": json.dumps(payload, ensure_ascii=False)}
        )
    logger.info("数据库配置已保存到 system_config 表")


def load_from_db(engine: Engine) -> Optional[Dict[str, Any]]:
    """从数据库 system_config 表读取数据库配置。返回包含明文 password 的 dict，或 None。"""
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT config_value FROM system_config WHERE config_key = :key"),
                {"key": KEY_DB_CONFIG}
            ).fetchone()
    except Exception as e:
        logger.warning("从 system_config 表读取配置失败: %s", e)
        return None

    if not row:
        return None

    try:
        payload = json.loads(row[0])
    except (json.JSONDecodeError, TypeError) as e:
        logger.warning("system_config 表配置数据格式错误: %s", e)
        return None

    result = {
        "host": payload.get("host", DEFAULT_CONFIG["host"]),
        "port": payload.get("port", DEFAULT_CONFIG["port"]),
        "username": payload.get("username", DEFAULT_CONFIG["username"]),
        "database": payload.get("database", DEFAULT_CONFIG["database"]),
    }

    enc_pw = payload.get("password_encrypted")
    if enc_pw:
        try:
            result["password"] = decrypt_password(enc_pw)
        except Exception as e:
            logger.warning("解密 DB 存储的密码失败: %s", e)
            return None

    return result


def clear_local() -> None:
    """删除本地加密配置文件"""
    if LOCAL_CONFIG_FILE.exists():
        LOCAL_CONFIG_FILE.unlink()
        logger.info("已删除本地加密配置文件")


def to_connection_url(config_dict: Dict[str, Any]) -> str:
    """从配置字典生成 SQLAlchemy 连接 URL"""
    import urllib.parse
    encoded_password = urllib.parse.quote(config_dict.get("password", ""), safe="")
    return (
        f"mysql+pymysql://{config_dict['username']}:{encoded_password}"
        f"@{config_dict['host']}:{config_dict['port']}/{config_dict['database']}"
        f"?charset=utf8mb4"
    )
