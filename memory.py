import sqlite3
import threading
from datetime import datetime, timezone


class TokenMemory:
    """Small SQLite-backed memory store for Token."""

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
                CREATE INDEX IF NOT EXISTS idx_conversation_channel ON conversation(channel_id, id DESC);
                CREATE INDEX IF NOT EXISTS idx_conversation_user ON conversation(user_id, id DESC);
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
                CREATE INDEX IF NOT EXISTS idx_attachments_hash ON attachments(sha256);
                CREATE TABLE IF NOT EXISTS fan_art_state (
                    user_id INTEGER PRIMARY KEY,
                    requested INTEGER NOT NULL DEFAULT 0,
                    received INTEGER NOT NULL DEFAULT 0,
                    last_requested TEXT,
                    last_received TEXT
                );
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
                WHERE channel_id=? ORDER BY id DESC LIMIT ?
            """, (channel_id, limit)).fetchall()
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    def recent_users(self, channel_id, limit=12):
        with self.lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT user_id, username, display_name, MAX(id) AS last_id
                FROM conversation
                WHERE channel_id=? AND user_id IS NOT NULL AND role='user'
                GROUP BY user_id ORDER BY last_id DESC LIMIT ?
            """, (channel_id, limit)).fetchall()
        return [{"user_id": r[0], "username": r[1], "display_name": r[2]} for r in rows]

    def recent_user_messages(self, user_id, limit=8):
        with self.lock, self._connect() as conn:
            rows = conn.execute("""
                SELECT content FROM conversation
                WHERE user_id=? AND role='user'
                ORDER BY id DESC LIMIT ?
            """, (user_id, limit)).fetchall()
        return [r[0] for r in reversed(rows)]

    def remember_attachment(self, channel_id, user_id, filename, content_type, size, sha256):
        now = self._now()
        with self.lock, self._connect() as conn:
            row = None
            if sha256:
                row = conn.execute("""
                    SELECT id FROM attachments
                    WHERE sha256=? AND channel_id=? ORDER BY id DESC LIMIT 1
                """, (sha256, channel_id)).fetchone()
            if row:
                conn.execute("""
                    UPDATE attachments SET last_seen=?, times_seen=times_seen+1,
                    filename=?, content_type=?, size=?, user_id=? WHERE id=?
                """, (now, filename or '', content_type or 'unknown', size or 0, user_id, row[0]))
                return True
            conn.execute("""
                INSERT INTO attachments(
                    channel_id,user_id,filename,content_type,size,sha256,
                    first_seen,last_seen,times_seen
                ) VALUES (?,?,?,?,?,?,?,?,1)
            """, (channel_id, user_id, filename or '', content_type or 'unknown', size or 0,
                  sha256, now, now))
            return False

    def fan_art_requested(self, user_id):
        with self.lock, self._connect() as conn:
            row = conn.execute("SELECT requested FROM fan_art_state WHERE user_id=?", (user_id,)).fetchone()
        return bool(row and row[0])

    def mark_fan_art_requested(self, user_id):
        now = self._now()
        with self.lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO fan_art_state(user_id,requested,received,last_requested)
                VALUES (?,1,0,?)
                ON CONFLICT(user_id) DO UPDATE SET requested=1,last_requested=excluded.last_requested
            """, (user_id, now))

    def mark_fan_art_received(self, user_id):
        now = self._now()
        with self.lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO fan_art_state(user_id,requested,received,last_received)
                VALUES (?,0,1,?)
                ON CONFLICT(user_id) DO UPDATE SET received=1,last_received=excluded.last_received
            """, (user_id, now))

    def forget_channel(self, channel_id):
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM conversation WHERE channel_id=?", (channel_id,))
            conn.execute("DELETE FROM attachments WHERE channel_id=?", (channel_id,))

    def forget_user(self, user_id):
        with self.lock, self._connect() as conn:
            conn.execute("DELETE FROM conversation WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM attachments WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
            conn.execute("DELETE FROM fan_art_state WHERE user_id=?", (user_id,))
