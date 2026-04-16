"""
Alembic 環境配置
"""
from logging.config import fileConfig
from sqlalchemy import engine_from_config
from sqlalchemy import pool
from alembic import context
import os
import sys

# 將專案根目錄加入路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base
from app.config import settings
from app.models import *  # 導入所有模型

# Alembic Config 物件
config = context.config

# 設定資料庫 URL
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 設定日誌
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目標元數據
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """離線遷移模式"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """線上遷移模式"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

