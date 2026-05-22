import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from config.settings import settings
from utils.logging import logger

class MemoryManager:
    """Manages session database, stores chat logs, shell runs, and command state in SQLite."""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.memory_db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Helper to establish a database connection with auto-mapping."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Enables accessing columns by name
        return conn

    def _init_db(self) -> None:
        """Initializes tables for sessions, messages, and executed commands if not exist."""
        logger.debug(f"Initializing SQLite database at: {self.db_path}")
        
        create_sessions_table = """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        create_messages_table = """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            role TEXT CHECK(role IN ('user', 'model', 'system')),
            content TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        """
        
        create_commands_table = """
        CREATE TABLE IF NOT EXISTS commands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            command TEXT NOT NULL,
            output TEXT,
            exit_code INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_blocked BOOLEAN DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );
        """
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(create_sessions_table)
            cursor.execute(create_messages_table)
            cursor.execute(create_commands_table)
            conn.commit()

    def create_session(self, session_id: str) -> None:
        """Registers a new active conversation session ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO sessions (id) VALUES (?)",
                (session_id,)
            )
            conn.commit()

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Appends a chat message (user, assistant, or system prompt) to the history."""
        self.create_session(session_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content)
            )
            conn.commit()

    def get_messages(self, session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves conversational messages for a session ordered by time."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY id ASC LIMIT ?",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def log_command(self, session_id: str, command: str, output: str, exit_code: Optional[int], is_blocked: bool = False) -> None:
        """Logs detailed shell command metadata and outputs to the storage."""
        self.create_session(session_id)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO commands (session_id, command, output, exit_code, is_blocked) VALUES (?, ?, ?, ?, ?)",
                (session_id, command, output, exit_code, 1 if is_blocked else 0)
            )
            conn.commit()

    def get_commands(self, session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Gets previously executed shell runs in this session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT command, output, exit_code, timestamp, is_blocked FROM commands WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def clear_session(self, session_id: str) -> None:
        """Deletes all messages and execution history related to a specific session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM commands WHERE session_id = ?", (session_id,))
            cursor.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            logger.info(f"Memory cleared for session: {session_id}")
