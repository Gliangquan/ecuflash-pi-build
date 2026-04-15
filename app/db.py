from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection

from app.settings import settings


engine = create_engine(
    settings.mysql_dsn,
    pool_pre_ping=True,
    pool_recycle=3600,
    future=True,
)


@contextmanager
def get_conn() -> Generator[Connection, None, None]:
    conn = engine.connect()
    try:
        yield conn
    finally:
        conn.close()
