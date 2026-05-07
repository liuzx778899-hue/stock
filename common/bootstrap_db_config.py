#!/usr/bin/env python3
"""
数据库配置初始化脚本
用于首次配置数据库连接参数，将密码加密存储到本地文件

用法:
    python common/bootstrap_db_config.py
    python common/bootstrap_db_config.py --password YOUR_PASSWORD
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.db_config_store import save_local, load_local, DEFAULT_CONFIG


def main():
    parser = argparse.ArgumentParser(description="初始化数据库配置")
    parser.add_argument("--host", default=DEFAULT_CONFIG["host"], help="数据库主机")
    parser.add_argument("--port", type=int, default=DEFAULT_CONFIG["port"], help="数据库端口")
    parser.add_argument("--username", default=DEFAULT_CONFIG["username"], help="数据库用户名")
    parser.add_argument("--database", default=DEFAULT_CONFIG["database"], help="数据库名称")
    parser.add_argument("--password", help="数据库密码（不提供则交互输入）")
    args = parser.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("请输入数据库密码: ")
        if not password:
            print("错误: 密码不能为空")
            sys.exit(1)

    config = {
        "host": args.host,
        "port": args.port,
        "username": args.username,
        "password": password,
        "database": args.database,
    }

    save_local(config)
    print(f"配置已加密保存到: .db_config.enc")

    # 验证
    loaded = load_local()
    if loaded and loaded.get("password") == password:
        print("验证成功: 配置读取正常")
    else:
        print("警告: 配置验证失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
