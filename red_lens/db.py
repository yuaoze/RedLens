# -*- coding: utf-8 -*-
"""
Database module for RedLens
Handles SQLite database operations for bloggers and notes
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


# Database file path
DB_PATH = Path(__file__).parent / "red_lens.db"


@contextmanager
def get_connection():
    """Context manager for database connections"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database and create tables if they don't exist"""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Create bloggers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bloggers (
                user_id TEXT PRIMARY KEY,
                nickname TEXT NOT NULL,
                avatar_url TEXT,
                initial_fans INTEGER DEFAULT 0,
                current_fans INTEGER DEFAULT 0,
                source_keyword TEXT,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'scraped', 'error')),
                last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                note_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                desc TEXT,
                type TEXT CHECK(type IN ('video', 'image')),
                likes INTEGER DEFAULT 0,
                collects INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                create_time TIMESTAMP,
                crawled_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cover_url TEXT,
                local_cover_path TEXT,
                is_outlier BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES bloggers(user_id)
            )
        """)

        # Create indexes for better query performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bloggers_status
            ON bloggers(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_notes_user_id
            ON notes(user_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_notes_is_outlier
            ON notes(is_outlier)
        """)

        print(f"✓ Database initialized at: {DB_PATH}")


class BloggerDB:
    """Database operations for bloggers table"""

    @staticmethod
    def insert_blogger(
        user_id: str,
        nickname: str,
        avatar_url: Optional[str] = None,
        initial_fans: int = 0,
        source_keyword: Optional[str] = None
    ) -> bool:
        """Insert a new blogger into the database"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO bloggers
                    (user_id, nickname, avatar_url, initial_fans, current_fans, source_keyword)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (user_id, nickname, avatar_url, initial_fans, initial_fans, source_keyword))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error inserting blogger {user_id}: {e}")
            return False

    @staticmethod
    def get_blogger(user_id: str) -> Optional[Dict[str, Any]]:
        """Get a single blogger by user_id"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bloggers WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_pending_bloggers(limit: int = 5) -> List[Dict[str, Any]]:
        """Get bloggers with 'pending' status"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM bloggers
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def update_status(user_id: str, status: str) -> bool:
        """Update blogger status"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE bloggers
                    SET status = ?, last_update = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (status, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating blogger status {user_id}: {e}")
            return False

    @staticmethod
    def update_fans(user_id: str, current_fans: int) -> bool:
        """Update current fan count"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE bloggers
                    SET current_fans = ?, last_update = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (current_fans, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating fans for {user_id}: {e}")
            return False

    @staticmethod
    def get_all_bloggers() -> List[Dict[str, Any]]:
        """Get all bloggers"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bloggers ORDER BY last_update DESC")
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def count_by_status(status: str) -> int:
        """Count bloggers by status"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM bloggers WHERE status = ?", (status,))
            return cursor.fetchone()[0]


class NoteDB:
    """Database operations for notes table"""

    @staticmethod
    def insert_note(
        note_id: str,
        user_id: str,
        title: Optional[str] = None,
        desc: Optional[str] = None,
        note_type: Optional[str] = None,
        likes: int = 0,
        collects: int = 0,
        comments: int = 0,
        create_time: Optional[str] = None,
        cover_url: Optional[str] = None
    ) -> bool:
        """Insert a new note into the database"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO notes
                    (note_id, user_id, title, desc, type, likes, collects, comments,
                     create_time, cover_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (note_id, user_id, title, desc, note_type, likes, collects,
                      comments, create_time, cover_url))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error inserting note {note_id}: {e}")
            return False

    @staticmethod
    def get_notes_by_user(user_id: str) -> List[Dict[str, Any]]:
        """Get all notes for a specific user"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM notes
                WHERE user_id = ?
                ORDER BY create_time DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_note(note_id: str) -> Optional[Dict[str, Any]]:
        """Get a single note by note_id"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notes WHERE note_id = ?", (note_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def update_outlier_status(note_id: str, is_outlier: bool) -> bool:
        """Mark a note as outlier (爆款)"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE notes
                    SET is_outlier = ?
                    WHERE note_id = ?
                """, (1 if is_outlier else 0, note_id))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating outlier status for {note_id}: {e}")
            return False

    @staticmethod
    def update_local_cover_path(note_id: str, local_path: str) -> bool:
        """Update local cover image path"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE notes
                    SET local_cover_path = ?
                    WHERE note_id = ?
                """, (local_path, note_id))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating local cover path for {note_id}: {e}")
            return False

    @staticmethod
    def get_outlier_notes(user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all outlier notes, optionally filtered by user"""
        with get_connection() as conn:
            cursor = conn.cursor()
            if user_id:
                cursor.execute("""
                    SELECT * FROM notes
                    WHERE is_outlier = 1 AND user_id = ?
                    ORDER BY likes DESC
                """, (user_id,))
            else:
                cursor.execute("""
                    SELECT * FROM notes
                    WHERE is_outlier = 1
                    ORDER BY likes DESC
                """)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_avg_likes_by_user(user_id: str) -> float:
        """Calculate average likes for a user's notes"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT AVG(likes) FROM notes
                WHERE user_id = ?
            """, (user_id,))
            result = cursor.fetchone()[0]
            return float(result) if result else 0.0

    @staticmethod
    def count_notes_by_user(user_id: str) -> int:
        """Count total notes for a user"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM notes
                WHERE user_id = ?
            """, (user_id,))
            return cursor.fetchone()[0]


if __name__ == "__main__":
    # Test database initialization
    init_db()

    # Test inserting a blogger
    test_user_id = "test_user_123"
    success = BloggerDB.insert_blogger(
        user_id=test_user_id,
        nickname="测试博主",
        initial_fans=1000,
        source_keyword="街头摄影"
    )
    print(f"Insert blogger: {success}")

    # Test retrieving blogger
    blogger = BloggerDB.get_blogger(test_user_id)
    print(f"Retrieved blogger: {blogger}")

    # Test inserting a note
    test_note_id = "note_456"
    success = NoteDB.insert_note(
        note_id=test_note_id,
        user_id=test_user_id,
        title="测试笔记",
        likes=500,
        collects=100,
        comments=50
    )
    print(f"Insert note: {success}")

    # Test retrieving notes
    notes = NoteDB.get_notes_by_user(test_user_id)
    print(f"Retrieved notes: {len(notes)} note(s)")

    print("\n✓ All database tests passed!")
