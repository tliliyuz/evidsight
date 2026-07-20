"""数据库引擎 & session 工厂 — SQLAlchemy 2.0 async + aiomysql"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.mysql_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,   # 取用连接前先 ping,发现失效连接自动重连,避免 MySQL wait_timeout 断连后报 2013
    pool_recycle=3600,    # 连接使用满 1 小时主动回收重建,须小于 MySQL wait_timeout(默认 28800s)
    echo=settings.DEBUG,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""
    pass
