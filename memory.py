import sqlite3
import threading
from datetime import datetime, timezone


class TokenMemory:
    """Small SQLite-backed memory store for Token.

    Keeps recent conversation, user identity metadata, and attachment fingerprints
    so memory survives bot restarts without requiring another dependency.
    """

    def __init__(self, path="token_memory.db"):
        self.path = path
        self.lock = threading.RLock()
        self._init_db()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self):
        with self.lock, self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS conversation (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER,
                    username TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_channel
                    ON conversation(channel_id, id DESC);

                CREATE INDEX IF NOT EXISTS idx_conversation_user
                    ON conversation(user_id, id DESC);

                CREATE TABLE IF NOT EXISTS attachments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_id INTEGER NOT NULL,
                    user_id INTEGER,
                    filename TEXT NOT NULL DEFAULT '',
                    content_type TEXT NOT NULL DEFAULT 'unknown',
                    size INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    times_seen INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_attachments_hash
                    ON attachments(sha256);
            """)

    def remember_user(self, user_id, username, display_name):
        now = self._now()
        with self.lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO users(user_id, username, display_name, first_seen, last_seen, message_count)
                VALUES (?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    display_name=excluded.display_name,
                    last_seen=excluded.last_seen,
                    message_count=users.message_count + 1
            """, (user_id, username or '', display_name or '', now, now))

    def remember_message(self, channel_id, user_id, username, role, content):
        with self.lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO conversation(channel_id, user_id, username, role, content, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (channel_id, user_id, username or '', role, content, self._now()))

    def load_history(self, channel_id, limit=40):
        with self.lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT role, content FROM conversation
                WHERE channel_id = ?
                ORDER BY id DESC LIMIT ?
            """, (channel_id, limit)).fetchall()
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    def recent_users(self, channel_id, limit=12):
        with self.lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT user_id, username, display_name, MAX(id) AS last_id
                FROM conversation
                WHERE channel_id = ? AND user_id IS NOT NULL AND role = 'user'
                GROUP BY user_id
                ORDER BY last_id DESC LIMIT ?
            """, (channel_id, limit)).fetchall()
        return [
            {"user_id": row[0], "username": row[1], "display_name": row[2]}
            for row in rows
        ]

    def remember_attachment(self, channel_id, user_id, filename, content_type, size, sha256):
        now = self._now()
        with self.lock, self._connect() as conn:
            if sha256:
                row = conn.execute("""
                    SELECT id, times_seen FROM attachments
                    WHERE sha256 = ? AND channel_id = ?
                    ORDER BY id DESC LIMIT 1
                """, (sha256, channel_id)).fetchone()
            else:
                row = None

            if row:
                conn.execute("""
                    UPDATE attachments
                    SET last_seen=?, times_seen=times_seen+1,
                        filename=?, content_type=?, size=?, user_id=?
                    WHERE id=?
                """, (now, filename or '', content_type or 'unknown', size or 0, user_id, row[0]))
                return True

            conn.execute("""
                INSERT INTO attachments(
                    channel_id, user_id, filename, content_type, size, sha256,
                    first_seen, last_seen, times_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (channel_id, user_id, filename or '', content_type or 'unknown', size or 0,
                  sha256, now, now))
            return False

    def attachment_seen(self, channel_id, sha256):
        if not sha256:
            return False
        with self.lock, self._connect() as conn:
            row = conn.execute("""
                SELECT 1 FROM attachments WHERE channel_id=? AND sha256=? LIMIT 1
            """, (channel_id, sha256)).fetchone()
        return row is not None

    def forget_channel(self, channel_id):
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM conversation WHERE channel_id=?", (channel_id,))
            conn.execute("DELETE FROM attachments WHERE channel_id=?", (channel_id,))

    def forget_user(self, user_id):
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM conversation WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM attachments WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
