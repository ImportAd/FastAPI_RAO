"""
db/database.py
--------------
SQLite база данных: пользователи, история документов, сессии генерации.
"""
from __future__ import annotations

import sqlite3
import json
import hashlib
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()


# ──────────── Data classes ────────────

@dataclass
class User:
    id: int
    username: str
    display_name: str
    password_hash: str
    salt: str
    is_active: bool = True
    created_at: str = ""

    def check_password(self, password: str) -> bool:
        return _hash_password(password, self.salt) == self.password_hash

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "is_active": self.is_active,
            "created_at": self.created_at,
        }


@dataclass
class DocumentRecord:
    id: int
    user_id: int
    template_code: str
    template_title: str
    answers_json: str  # JSON snapshot of filled fields
    status: str  # "done", "failed"
    error_text: str = ""
    generation_time_ms: int = 0  # milliseconds
    filename: str = ""
    created_at: str = ""
    is_auto_generated: bool = False  # True for auto-generated ACTs
    display_filename: str = ""

    @property
    def answers(self) -> Dict[str, Any]:
        try:
            return json.loads(self.answers_json)
        except Exception:
            return {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "template_code": self.template_code,
            "template_title": self.template_title,
            "status": self.status,
            "error_text": self.error_text,
            "generation_time_ms": self.generation_time_ms,
            "filename": self.filename,
            "display_filename": self.display_filename,
            "created_at": self.created_at,
            "is_auto_generated": self.is_auto_generated,
        }

    def to_dict_with_answers(self) -> dict:
        d = self.to_dict()
        d["answers"] = self.answers
        return d


# ──────────── Database ────────────

class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_tables(self):
        conn = self._conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    template_code TEXT NOT NULL,
                    template_title TEXT NOT NULL DEFAULT '',
                    answers_json TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'done',
                    error_text TEXT NOT NULL DEFAULT '',
                    generation_time_ms INTEGER NOT NULL DEFAULT 0,
                    filename TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    is_auto_generated INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                    display_filename TEXT NOT NULL DEFAULT '',
                );

                CREATE INDEX IF NOT EXISTS idx_documents_user
                    ON documents(user_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_documents_status
                    ON documents(status);
            """)
            cur = conn.execute("PRAGMA table_info(documents)")
            cols = {row[1] for row in cur.fetchall()}
            if "display_filename" not in cols:
                conn.execute(
                    "ALTER TABLE documents ADD COLUMN display_filename TEXT NOT NULL DEFAULT ''"
                )
            conn.commit()
        finally:
            conn.close()

    # ──── Users ────

    def create_user(self, username: str, password: str, display_name: str = "") -> User:
        salt = secrets.token_hex(16)
        pw_hash = _hash_password(password, salt)
        now = _now_iso()
        conn = self._conn()
        try:
            cur = conn.execute(
                "INSERT INTO users (username, display_name, password_hash, salt, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (username, display_name or username, pw_hash, salt, now),
            )
            conn.commit()
            return User(
                id=cur.lastrowid,
                username=username,
                display_name=display_name or username,
                password_hash=pw_hash,
                salt=salt,
                is_active=True,
                created_at=now,
            )
        finally:
            conn.close()

    def _row_to_user(self, row) -> User:
        """Convert a DB row to User, properly handling is_active int→bool."""
        d = dict(row)
        d['is_active'] = bool(d.get('is_active', 1))
        return User(**d)

    def get_user_by_username(self, username: str) -> Optional[User]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if not row:
                return None
            return self._row_to_user(row)
        finally:
            conn.close()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if not row:
                return None
            return self._row_to_user(row)
        finally:
            conn.close()

    def list_users(self) -> List[User]:
        conn = self._conn()
        try:
            rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
            return [self._row_to_user(r) for r in rows]
        finally:
            conn.close()

    def update_user(self, user_id: int, *, username: str = None, display_name: str = None,
                    password: str = None, is_active: bool = None) -> bool:
        conn = self._conn()
        try:
            updates = []
            params = []
            if username is not None:
                updates.append("username = ?")
                params.append(username)
            if display_name is not None:
                updates.append("display_name = ?")
                params.append(display_name)
            if password is not None:
                salt = secrets.token_hex(16)
                pw_hash = _hash_password(password, salt)
                updates.append("password_hash = ?")
                params.append(pw_hash)
                updates.append("salt = ?")
                params.append(salt)
            if is_active is not None:
                updates.append("is_active = ?")
                params.append(1 if is_active else 0)
            if not updates:
                return False
            params.append(user_id)
            conn.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            return True
        finally:
            conn.close()

    def delete_user(self, user_id: int) -> bool:
        conn = self._conn()
        try:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return True
        finally:
            conn.close()

    # ──── Documents ────

    def save_document(
        self,
        user_id: int,
        template_code: str,
        template_title: str,
        answers: Dict[str, Any],
        status: str,
        error_text: str = "",
        generation_time_ms: int = 0,
        filename: str = "",
        is_auto_generated: bool = False,
        display_filename: str = "",
    ) -> DocumentRecord:
        now = _now_iso()
        answers_json = json.dumps(answers, ensure_ascii=False)
        conn = self._conn()
        try:
            cur = conn.execute(
                "INSERT INTO documents "
                "(user_id, template_code, template_title, answers_json, status, "
                "error_text, generation_time_ms, filename, created_at, is_auto_generated, display_filename) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, template_code, template_title, answers_json,
                 status, error_text, generation_time_ms, filename, now,
                 1 if is_auto_generated else 0, display_filename),
            )
            conn.commit()
            return DocumentRecord(
                id=cur.lastrowid,
                user_id=user_id,
                template_code=template_code,
                template_title=template_title,
                answers_json=answers_json,
                status=status,
                error_text=error_text,
                generation_time_ms=generation_time_ms,
                filename=filename,
                created_at=now,
                is_auto_generated=is_auto_generated,
                display_filename=display_filename,
            )
        finally:
            conn.close()

    def _row_to_doc(self, row) -> DocumentRecord:
        """Convert a DB row to DocumentRecord, properly handling is_auto_generated int→bool."""
        d = dict(row)
        d['is_auto_generated'] = bool(d.get('is_auto_generated', 0))
        return DocumentRecord(**d)

    def get_user_documents(self, user_id: int, limit: int = 50,
                           include_auto: bool = False) -> List[DocumentRecord]:
        conn = self._conn()
        try:
            sql = "SELECT * FROM documents WHERE user_id = ?"
            params: list = [user_id]
            if not include_auto:
                sql += " AND is_auto_generated = 0"
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_doc(r) for r in rows]
        finally:
            conn.close()

    def get_document(self, doc_id: int) -> Optional[DocumentRecord]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            if not row:
                return None
            return self._row_to_doc(row)
        finally:
            conn.close()

    def get_all_documents(self, limit: int = 100, status: str = None) -> List[DocumentRecord]:
        conn = self._conn()
        try:
            sql = "SELECT * FROM documents"
            params: list = []
            if status:
                sql += " WHERE status = ?"
                params.append(status)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_doc(r) for r in rows]
        finally:
            conn.close()
    
    def delete_user_documents(self, user_id: int) -> int:
        """Удалить все документы пользователя. Возвращает количество удалённых."""
        conn = self._conn()
        try:
            cur = conn.execute("DELETE FROM documents WHERE user_id = ?", (user_id,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def get_generation_stats(self) -> dict:
        conn = self._conn()
        try:
            total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            done = conn.execute("SELECT COUNT(*) FROM documents WHERE status='done'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM documents WHERE status='failed'").fetchone()[0]
            avg_time = conn.execute(
                "SELECT AVG(generation_time_ms) FROM documents WHERE status='done' AND generation_time_ms > 0"
            ).fetchone()[0]
            return {
                "total_generations": total,
                "successful": done,
                "failed": failed,
                "avg_generation_time_ms": round(avg_time or 0),
            }
        finally:
            conn.close()
