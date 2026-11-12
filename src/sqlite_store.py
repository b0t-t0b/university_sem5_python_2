"""SQLite + SQLAlchemy ORM data access layer for Variant 22."""

import threading
import time

from sqlalchemy import ForeignKey, Integer, String, create_engine, event
from sqlalchemy import func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from src.constants import (
    DEFAULT_SQLITE_URL,
    ONE,
    QUERY_TIME_WINDOW_SECONDS,
    TASK_STATUS_OK,
)


class Base(DeclarativeBase):
    """Declarative base class for SQLAlchemy ORM models."""


class SessionModel(Base):
    """ORM model representing Session table."""

    __tablename__ = "sessions"

    uid: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    locale: Mapped[str] = mapped_column(String, nullable=False)
    user_agent: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self):
        """Convert Session ORM row to dictionary."""
        return {
            "uid": self.uid,
            "timestamp": self.timestamp,
            "locale": self.locale,
            "user_agent": self.user_agent,
        }


class RequestModel(Base):
    """ORM model representing Request table."""

    __tablename__ = "requests"

    uid: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(String, nullable=False)
    session: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("sessions.uid", ondelete="RESTRICT"),
        nullable=False,
    )
    triggered: Mapped[int] = mapped_column(Integer, nullable=False)

    def to_dict(self):
        """Convert Request ORM row to dictionary."""
        return {
            "uid": self.uid,
            "timestamp": self.timestamp,
            "content": self.content,
            "session": self.session,
            "triggered": self.triggered,
        }


class AnswerModel(Base):
    """ORM model representing Answer table."""

    __tablename__ = "answers"

    uid: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    output: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    exception: Mapped[str] = mapped_column(String, nullable=False)
    request: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("requests.uid", ondelete="CASCADE"),
        nullable=False,
    )
    cache_hit: Mapped[int] = mapped_column(Integer, nullable=False)

    def to_dict(self):
        """Convert Answer ORM row to dictionary."""
        return {
            "uid": self.uid,
            "timestamp": self.timestamp,
            "output": self.output,
            "status": self.status,
            "exception": self.exception,
            "request": self.request,
            "cache_hit": self.cache_hit,
        }


def _enable_sqlite_fk(dbapi_conn, _conn_record):
    """Enable SQLite foreign key enforcement per connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _apply_filters(stmt, model_cls, filters, cast_map):
    """Attach WHERE clauses to SQLAlchemy select statement."""
    if not filters:
        return stmt
    for key, val in filters.items():
        if key in cast_map:
            col = getattr(model_cls, key)
            stmt = stmt.where(col == cast_map[key](val))
    return stmt


class SQLiteDataStore:
    """Thread-safe SQLite data access layer powered by SQLAlchemy ORM."""

    def __init__(self, db_url=DEFAULT_SQLITE_URL):
        """Initialize SQLAlchemy engine, schema, and session factory."""
        self.db_url = db_url
        self._lock = threading.Lock()
        self.engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},
        )
        event.listen(self.engine, "connect", _enable_sqlite_fk)
        Base.metadata.create_all(self.engine)
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False
        )

    def dispose(self):
        """Dispose underlying SQLAlchemy connection pool."""
        self.engine.dispose()

    def clear_all(self):
        """Delete all rows from Answer, Request, and Session tables."""
        with self._lock:
            with self._session_factory() as db:
                db.query(AnswerModel).delete()
                db.query(RequestModel).delete()
                db.query(SessionModel).delete()
                db.commit()

    def create_session(self, uid, timestamp, locale, user_agent):
        """Insert a new Session row via SQLAlchemy ORM."""
        int_uid = int(uid)
        with self._lock:
            with self._session_factory() as db:
                if db.get(SessionModel, int_uid) is not None:
                    raise ValueError(f"Session {int_uid} already exists")
                row = SessionModel(
                    uid=int_uid,
                    timestamp=int(timestamp),
                    locale=str(locale),
                    user_agent=str(user_agent),
                )
                db.add(row)
                db.commit()
                return row.to_dict()

    def remove_session(self, uid):
        """Delete Session row by uid if no Request references it."""
        int_uid = int(uid)
        with self._lock:
            with self._session_factory() as db:
                row = db.get(SessionModel, int_uid)
                if row is None:
                    raise KeyError(f"Session {int_uid} not found")
                linked = db.execute(
                    select(RequestModel.uid).where(
                        RequestModel.session == int_uid
                    )
                ).first()
                if linked is not None:
                    raise ValueError(
                        f"Session {int_uid} referenced by request"
                    )
                db.delete(row)
                db.commit()
                return True

    def query_session(self, filters=None):
        """Query Session rows matching optional field filters."""
        cast_map = {
            "uid": int,
            "timestamp": int,
            "locale": str,
            "user_agent": str,
        }
        with self._lock:
            with self._session_factory() as db:
                stmt = select(SessionModel)
                stmt = _apply_filters(stmt, SessionModel, filters, cast_map)
                stmt = stmt.order_by(SessionModel.uid)
                rows = db.execute(stmt).scalars().all()
                return [row.to_dict() for row in rows]

    def correct_session(self, uid, updates=None):
        """Update fields of an existing Session row."""
        int_uid = int(uid)
        changes = updates or {}
        with self._lock:
            with self._session_factory() as db:
                row = db.get(SessionModel, int_uid)
                if row is None:
                    raise KeyError(f"Session {int_uid} not found")
                if changes.get("timestamp") is not None:
                    row.timestamp = int(changes["timestamp"])
                if changes.get("locale") is not None:
                    row.locale = str(changes["locale"])
                if changes.get("user_agent") is not None:
                    row.user_agent = str(changes["user_agent"])
                db.commit()
                return row.to_dict()

    def create_request(self, uid, timestamp, content, session, triggered):
        """Insert a new Request row validating foreign key Session."""
        int_uid = int(uid)
        int_sess = int(session)
        with self._lock:
            with self._session_factory() as db:
                if db.get(RequestModel, int_uid) is not None:
                    raise ValueError(f"Request {int_uid} already exists")
                if db.get(SessionModel, int_sess) is None:
                    raise ValueError(f"Session {int_sess} does not exist")
                row = RequestModel(
                    uid=int_uid,
                    timestamp=int(timestamp),
                    content=str(content),
                    session=int_sess,
                    triggered=int(triggered),
                )
                db.add(row)
                db.commit()
                return row.to_dict()

    def remove_request(self, uid):
        """Delete Request row and cascade-delete linked Answer rows."""
        int_uid = int(uid)
        with self._lock:
            with self._session_factory() as db:
                row = db.get(RequestModel, int_uid)
                if row is None:
                    raise KeyError(f"Request {int_uid} not found")
                db.query(AnswerModel).filter(
                    AnswerModel.request == int_uid
                ).delete()
                db.delete(row)
                db.commit()
                return True

    def query_request(self, session, filters=None):
        """Query Request rows for session matching optional filters."""
        sess_id = int(session)
        cast_map = {
            "uid": int,
            "timestamp": int,
            "content": str,
            "triggered": int,
        }
        with self._lock:
            with self._session_factory() as db:
                stmt = select(RequestModel).where(
                    RequestModel.session == sess_id
                )
                stmt = _apply_filters(stmt, RequestModel, filters, cast_map)
                stmt = stmt.order_by(RequestModel.uid)
                rows = db.execute(stmt).scalars().all()
                return [row.to_dict() for row in rows]

    def correct_request(self, uid, updates=None):
        """Update fields of an existing Request row."""
        int_uid = int(uid)
        changes = updates or {}
        with self._lock:
            with self._session_factory() as db:
                row = db.get(RequestModel, int_uid)
                if row is None:
                    raise KeyError(f"Request {int_uid} not found")
                if changes.get("session") is not None:
                    new_sess = int(changes["session"])
                    if db.get(SessionModel, new_sess) is None:
                        raise ValueError(f"Session {new_sess} does not exist")
                    row.session = new_sess
                if changes.get("timestamp") is not None:
                    row.timestamp = int(changes["timestamp"])
                if changes.get("content") is not None:
                    row.content = str(changes["content"])
                if changes.get("triggered") is not None:
                    row.triggered = int(changes["triggered"])
                db.commit()
                return row.to_dict()

    def next_answer_uid(self):
        """Return next integer primary key for Answer table."""
        with self._lock:
            with self._session_factory() as db:
                max_uid = db.execute(
                    select(func.max(AnswerModel.uid))
                ).scalar()
                return ONE if max_uid is None else int(max_uid) + ONE

    def find_cached_answer(self, content):
        """Return a prior successful Answer for matching request content."""
        with self._lock:
            with self._session_factory() as db:
                stmt = (
                    select(AnswerModel)
                    .join(
                        RequestModel,
                        AnswerModel.request == RequestModel.uid,
                    )
                    .where(
                        AnswerModel.status == TASK_STATUS_OK,
                        RequestModel.content == str(content),
                    )
                    .order_by(AnswerModel.uid)
                )
                row = db.execute(stmt).scalars().first()
                return None if row is None else row.to_dict()

    def create_answer(self, payload):
        """Insert a new Answer row from payload dictionary."""
        int_uid = int(payload["uid"])
        int_req = int(payload["request"])
        with self._lock:
            with self._session_factory() as db:
                if db.get(AnswerModel, int_uid) is not None:
                    raise ValueError(f"Answer {int_uid} already exists")
                if db.get(RequestModel, int_req) is None:
                    raise ValueError(f"Request {int_req} does not exist")
                row = AnswerModel(
                    uid=int_uid,
                    timestamp=int(payload["timestamp"]),
                    output=str(payload["output"]),
                    status=str(payload["status"]),
                    exception=str(payload["exception"]),
                    request=int_req,
                    cache_hit=int(payload["cache_hit"]),
                )
                db.add(row)
                db.commit()
                return row.to_dict()

    def query_answer(self, request_uid, filters=None):
        """Query Answer rows for request_uid matching optional filters."""
        req_id = int(request_uid)
        cast_map = {
            "uid": int,
            "timestamp": int,
            "output": str,
            "status": str,
            "exception": str,
            "cache_hit": int,
        }
        with self._lock:
            with self._session_factory() as db:
                stmt = select(AnswerModel).where(
                    AnswerModel.request == req_id
                )
                stmt = _apply_filters(stmt, AnswerModel, filters, cast_map)
                stmt = stmt.order_by(AnswerModel.uid)
                rows = db.execute(stmt).scalars().all()
                return [row.to_dict() for row in rows]

    def query_report(self, now=None):
        """Execute relational algebra report query (formula 22) via ORM."""
        ref_time = int(time.time()) if now is None else int(now)
        threshold = ref_time - QUERY_TIME_WINDOW_SECONDS
        with self._lock:
            with self._session_factory() as db:
                recent_subq = (
                    select(SessionModel)
                    .where(SessionModel.timestamp >= threshold)
                    .subquery()
                )
                stmt = (
                    select(RequestModel.content, recent_subq.c.locale)
                    .outerjoin(
                        recent_subq,
                        RequestModel.session == recent_subq.c.uid,
                    )
                    .order_by(RequestModel.uid)
                )
                rows = db.execute(stmt).all()
                return [
                    {"content": content, "locale": locale}
                    for content, locale in rows
                ]


__all__ = [
    "AnswerModel",
    "Base",
    "RequestModel",
    "SQLiteDataStore",
    "SessionModel",
]
