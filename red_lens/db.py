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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes_collected INTEGER DEFAULT 0,
                notes_target INTEGER DEFAULT 100,
                last_scrape_time TIMESTAMP,
                scrape_status TEXT DEFAULT 'not_started',
                failure_reason TEXT
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
                note_url TEXT,
                is_outlier BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES bloggers(user_id)
            )
        """)

        # Create AI reports cache table (v1.2.4: Updated for multi-provider support)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                report_mode TEXT NOT NULL DEFAULT 'traffic',
                provider TEXT NOT NULL DEFAULT 'deepseek',
                model_name TEXT,
                report_content TEXT NOT NULL,
                note_covers TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, report_mode, provider, model_name),
                FOREIGN KEY (user_id) REFERENCES bloggers(user_id)
            )
        """)

        # Migrations for v1.2.0
        # Add note_url column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE notes ADD COLUMN note_url TEXT")
            print("✓ Added note_url column to notes table")
        except sqlite3.OperationalError:
            pass

        # Migrations for v1.2.4
        # Migrate old ai_reports table to new schema if needed
        try:
            # Check if old schema exists (user_id as PRIMARY KEY)
            cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='ai_reports'")
            table_sql = cursor.fetchone()[0]
            if 'user_id TEXT PRIMARY KEY' in table_sql:
                print("⚠ Migrating ai_reports table to v1.2.4 schema...")

                # Backup old data
                cursor.execute("ALTER TABLE ai_reports RENAME TO ai_reports_old")

                # Create new table with updated schema
                cursor.execute("""
                    CREATE TABLE ai_reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL,
                        report_mode TEXT NOT NULL DEFAULT 'traffic',
                        provider TEXT NOT NULL DEFAULT 'deepseek',
                        model_name TEXT,
                        report_content TEXT NOT NULL,
                        generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, report_mode, provider, model_name),
                        FOREIGN KEY (user_id) REFERENCES bloggers(user_id)
                    )
                """)

                # Migrate data (assume old reports are deepseek/traffic mode)
                cursor.execute("""
                    INSERT INTO ai_reports (user_id, report_mode, provider, model_name, report_content, generated_at)
                    SELECT user_id, 'traffic', 'deepseek', model, report_content, generated_at
                    FROM ai_reports_old
                """)

                # Drop old table
                cursor.execute("DROP TABLE ai_reports_old")
                print("✓ ai_reports table migrated to v1.2.4")
        except Exception as e:
            pass  # Table doesn't exist yet or migration not needed

        # Add report_mode, provider, model_name columns if old schema without migration
        try:
            cursor.execute("ALTER TABLE ai_reports ADD COLUMN report_mode TEXT DEFAULT 'traffic'")
            print("✓ Added report_mode column to ai_reports table")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE ai_reports ADD COLUMN provider TEXT DEFAULT 'deepseek'")
            print("✓ Added provider column to ai_reports table")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE ai_reports ADD COLUMN model_name TEXT")
            print("✓ Added model_name column to ai_reports table")
        except sqlite3.OperationalError:
            pass

        # Add note_covers column for v1.2.11 (封面展示功能)
        try:
            cursor.execute("ALTER TABLE ai_reports ADD COLUMN note_covers TEXT")
            print("✓ Added note_covers column to ai_reports table")
        except sqlite3.OperationalError:
            pass

        # Add scrape progress tracking columns
        try:
            cursor.execute("ALTER TABLE bloggers ADD COLUMN notes_collected INTEGER DEFAULT 0")
            print("✓ Added notes_collected column to bloggers table")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE bloggers ADD COLUMN notes_target INTEGER DEFAULT 100")
            print("✓ Added notes_target column to bloggers table")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE bloggers ADD COLUMN last_scrape_time TIMESTAMP")
            print("✓ Added last_scrape_time column to bloggers table")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE bloggers ADD COLUMN scrape_status TEXT DEFAULT 'not_started'")
            print("✓ Added scrape_status column to bloggers table")
        except sqlite3.OperationalError:
            pass

        try:
            cursor.execute("ALTER TABLE bloggers ADD COLUMN failure_reason TEXT")
            print("✓ Added failure_reason column to bloggers table")
        except sqlite3.OperationalError:
            pass

        # Create indexes for better query performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bloggers_status
            ON bloggers(status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_bloggers_scrape_status
            ON bloggers(scrape_status)
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
    def get_pending_bloggers_by_keyword(keyword: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Get pending bloggers, optionally filtered by keyword

        Args:
            keyword: Source keyword to filter by (None = all pending bloggers)
            limit: Maximum number of bloggers to return

        Returns:
            List of pending blogger dictionaries
        """
        with get_connection() as conn:
            cursor = conn.cursor()

            if keyword:
                cursor.execute("""
                    SELECT * FROM bloggers
                    WHERE status = 'pending' AND source_keyword LIKE ?
                    ORDER BY created_at ASC
                    LIMIT ?
                """, (f"%{keyword}%", limit))
            else:
                cursor.execute("""
                    SELECT * FROM bloggers
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT ?
                """, (limit,))

            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def count_pending_by_keyword(keyword: Optional[str] = None) -> int:
        """
        Count pending bloggers, optionally filtered by keyword

        Args:
            keyword: Source keyword to filter by (None = all pending bloggers)

        Returns:
            Count of pending bloggers
        """
        with get_connection() as conn:
            cursor = conn.cursor()

            if keyword:
                cursor.execute("""
                    SELECT COUNT(*) FROM bloggers
                    WHERE status = 'pending' AND source_keyword LIKE ?
                """, (f"%{keyword}%",))
            else:
                cursor.execute("""
                    SELECT COUNT(*) FROM bloggers
                    WHERE status = 'pending'
                """)

            return cursor.fetchone()[0]

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
    def update_blogger_info(
        user_id: str,
        nickname: str = None,
        avatar_url: str = None,
        current_fans: int = None
    ) -> bool:
        """Update blogger nickname, avatar, or fans"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                # Build update query with only provided fields
                update_fields = []
                values = []

                if nickname is not None:
                    update_fields.append("nickname = ?")
                    values.append(nickname)
                if avatar_url is not None:
                    update_fields.append("avatar_url = ?")
                    values.append(avatar_url)
                if current_fans is not None:
                    update_fields.append("current_fans = ?")
                    values.append(current_fans)

                if not update_fields:
                    return False

                update_fields.append("last_update = CURRENT_TIMESTAMP")
                values.append(user_id)

                query = f"""
                    UPDATE bloggers
                    SET {', '.join(update_fields)}
                    WHERE user_id = ?
                """
                cursor.execute(query, values)
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating blogger info for {user_id}: {e}")
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

    @staticmethod
    def reset_blogger_status(user_id: str) -> bool:
        """Reset blogger status to pending and clear notes"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                # Delete all notes for this blogger
                cursor.execute("DELETE FROM notes WHERE user_id = ?", (user_id,))
                # Reset status to pending
                cursor.execute("""
                    UPDATE bloggers
                    SET status = 'pending', last_update = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (user_id,))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error resetting blogger {user_id}: {e}")
            return False

    @staticmethod
    def delete_blogger(user_id: str) -> bool:
        """Delete a blogger and all their notes from database"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                # Delete all notes for this blogger
                cursor.execute("DELETE FROM notes WHERE user_id = ?", (user_id,))
                # Delete the blogger
                cursor.execute("DELETE FROM bloggers WHERE user_id = ?", (user_id,))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error deleting blogger {user_id}: {e}")
            return False

    @staticmethod
    def get_bloggers_by_keyword(keyword: str) -> List[Dict[str, Any]]:
        """Get bloggers filtered by source keyword"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM bloggers
                WHERE source_keyword LIKE ?
                ORDER BY last_update DESC
            """, (f"%{keyword}%",))
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def get_bloggers_by_status(status: str) -> List[Dict[str, Any]]:
        """Get bloggers filtered by status"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM bloggers
                WHERE status = ?
                ORDER BY last_update DESC
            """, (status,))
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def update_scrape_progress(
        user_id: str,
        notes_collected: int,
        notes_target: int,
        scrape_status: str,
        failure_reason: Optional[str] = None
    ) -> bool:
        """
        Update scrape progress for a blogger

        Args:
            user_id: User ID
            notes_collected: Number of notes collected so far
            notes_target: Target number of notes to collect
            scrape_status: Current scrape status (not_started/in_progress/completed/partial/failed)
            failure_reason: Optional reason for failure

        Returns:
            True if successful, False otherwise
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE bloggers
                    SET notes_collected = ?,
                        notes_target = ?,
                        scrape_status = ?,
                        failure_reason = ?,
                        last_scrape_time = CURRENT_TIMESTAMP,
                        last_update = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (notes_collected, notes_target, scrape_status, failure_reason, user_id))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating scrape progress for {user_id}: {e}")
            return False

    @staticmethod
    def get_resumable_bloggers(limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get bloggers that can resume scraping (partial status and not reached target)

        Args:
            limit: Maximum number of bloggers to return (None = no limit)

        Returns:
            List of resumable blogger dictionaries
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            if limit:
                cursor.execute("""
                    SELECT * FROM bloggers
                    WHERE scrape_status = 'partial'
                    AND notes_collected < notes_target
                    ORDER BY last_scrape_time DESC
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT * FROM bloggers
                    WHERE scrape_status = 'partial'
                    AND notes_collected < notes_target
                    ORDER BY last_scrape_time DESC
                """)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def count_resumable_bloggers() -> int:
        """Count bloggers that can resume scraping"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM bloggers
                WHERE scrape_status = 'partial'
                AND notes_collected < notes_target
            """)
            return cursor.fetchone()[0]

    @staticmethod
    def get_scrape_progress(user_id: str) -> Dict[str, Any]:
        """
        Get scrape progress for a specific blogger

        Args:
            user_id: User ID

        Returns:
            Dictionary with progress information
        """
        blogger = BloggerDB.get_blogger(user_id)
        if not blogger:
            return {
                "notes_collected": 0,
                "notes_target": 100,
                "scrape_status": "not_started",
                "failure_reason": None
            }

        return {
            "notes_collected": blogger.get("notes_collected", 0),
            "notes_target": blogger.get("notes_target", 100),
            "scrape_status": blogger.get("scrape_status", "not_started"),
            "failure_reason": blogger.get("failure_reason", None),
            "last_scrape_time": blogger.get("last_scrape_time", None)
        }

    @staticmethod
    def reset_scrape_progress(user_id: str) -> bool:
        """
        Reset scrape progress for a blogger (start from scratch)

        Args:
            user_id: User ID

        Returns:
            True if successful, False otherwise
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE bloggers
                    SET notes_collected = 0,
                        scrape_status = 'not_started',
                        failure_reason = NULL,
                        last_update = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                """, (user_id,))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error resetting scrape progress for {user_id}: {e}")
            return False


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
        cover_url: Optional[str] = None,
        note_url: Optional[str] = None
    ) -> bool:
        """Insert a new note into the database"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO notes
                    (note_id, user_id, title, desc, type, likes, collects, comments,
                     create_time, cover_url, note_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (note_id, user_id, title, desc, note_type, likes, collects,
                      comments, create_time, cover_url, note_url))
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
    def update_cover_url(note_id: str, cover_url: str) -> bool:
        """Update cover URL (用于刷新失效的临时链接)"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE notes
                    SET cover_url = ?
                    WHERE note_id = ?
                """, (cover_url, note_id))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error updating cover URL for {note_id}: {e}")
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

    @staticmethod
    def get_note_ids_by_user(user_id: str) -> List[str]:
        """
        Get all note IDs for a user
        Used for smart filtering during resume to avoid re-collecting existing notes

        Args:
            user_id: Xiaohongshu user ID

        Returns:
            List of note IDs (strings)
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT note_id FROM notes
                WHERE user_id = ?
            """, (user_id,))
            return [row[0] for row in cursor.fetchall()]

    @staticmethod
    def delete_notes_by_user(user_id: str) -> int:
        """Delete all notes for a specific user"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM notes WHERE user_id = ?", (user_id,))
                return cursor.rowcount
        except Exception as e:
            print(f"Error deleting notes for user {user_id}: {e}")
            return 0


class AIReportDB:
    """Database operations for AI reports cache table (v1.2.4: Multi-provider support)"""

    @staticmethod
    def save_report(user_id: str, report_file_path: str, report_mode: str = "traffic",
                    provider: str = "deepseek", model: str = None, note_covers: str = None) -> bool:
        """
        Save or update AI report metadata to database.
        Stores file path instead of content — file is the single source of truth.

        Args:
            user_id: User ID
            report_file_path: Path to the saved report file
            report_mode: Report mode ("traffic" | "personal")
            provider: AI provider name ("deepseek" | "kimi")
            model: AI model name
            note_covers: JSON string containing note cover information (v1.2.11)

        Returns:
            True if successful, False otherwise
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO ai_reports
                    (user_id, report_mode, provider, model_name, report_content, note_covers, generated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, report_mode, provider, model, report_file_path, note_covers))
                return cursor.rowcount > 0
        except Exception as e:
            print(f"Error saving AI report for {user_id}: {e}")
            return False

    @staticmethod
    def get_report(user_id: str, report_mode: str = "traffic",
                   provider: str = None, model: str = None) -> Optional[Dict[str, Any]]:
        """
        Get AI report metadata from database

        Args:
            user_id: User ID
            report_mode: Report mode
            provider: AI provider (None = get any provider)
            model: AI model (None = get any model)

        Returns:
            Report dict with keys: report_file_path, provider, model_name, note_covers, generated_at
        """
        with get_connection() as conn:
            cursor = conn.cursor()

            # Build query based on parameters
            if provider and model:
                cursor.execute("""
                    SELECT report_content AS report_file_path, provider, model_name, note_covers, generated_at
                    FROM ai_reports
                    WHERE user_id = ? AND report_mode = ? AND provider = ? AND model_name = ?
                """, (user_id, report_mode, provider, model))
            elif provider:
                cursor.execute("""
                    SELECT report_content AS report_file_path, provider, model_name, note_covers, generated_at
                    FROM ai_reports
                    WHERE user_id = ? AND report_mode = ? AND provider = ?
                    ORDER BY generated_at DESC
                    LIMIT 1
                """, (user_id, report_mode, provider))
            else:
                cursor.execute("""
                    SELECT report_content AS report_file_path, provider, model_name, note_covers, generated_at
                    FROM ai_reports
                    WHERE user_id = ? AND report_mode = ?
                    ORDER BY generated_at DESC
                    LIMIT 1
                """, (user_id, report_mode))

            row = cursor.fetchone()
            return dict(row) if row else None

    @staticmethod
    def get_reports_by_user(user_id: str) -> List[Dict[str, Any]]:
        """
        Get all reports for a specific user

        Args:
            user_id: User ID

        Returns:
            List of report info dicts with keys:
            report_mode, provider, model_name, generated_at, report_file_path, note_covers
        """
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT report_mode, provider, model_name, generated_at,
                       report_content AS report_file_path, note_covers
                FROM ai_reports
                WHERE user_id = ?
                ORDER BY generated_at DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def delete_report(user_id: str, report_mode: str = None,
                      provider: str = None, model: str = None) -> int:
        """
        Delete AI report(s)

        Args:
            user_id: User ID
            report_mode: Report mode (None = delete all modes)
            provider: Provider (None = delete all providers)
            model: Model (None = delete all models)

        Returns:
            Number of reports deleted
        """
        try:
            with get_connection() as conn:
                cursor = conn.cursor()

                # Build DELETE query based on parameters
                if report_mode and provider and model:
                    cursor.execute("""
                        DELETE FROM ai_reports
                        WHERE user_id = ? AND report_mode = ? AND provider = ? AND model_name = ?
                    """, (user_id, report_mode, provider, model))
                elif report_mode and provider:
                    cursor.execute("""
                        DELETE FROM ai_reports
                        WHERE user_id = ? AND report_mode = ? AND provider = ?
                    """, (user_id, report_mode, provider))
                elif report_mode:
                    cursor.execute("""
                        DELETE FROM ai_reports
                        WHERE user_id = ? AND report_mode = ?
                    """, (user_id, report_mode))
                else:
                    cursor.execute("""
                        DELETE FROM ai_reports
                        WHERE user_id = ?
                    """, (user_id,))

                return cursor.rowcount
        except Exception as e:
            print(f"Error deleting AI report: {e}")
            return 0

    @staticmethod
    def get_all_reports() -> List[Dict[str, Any]]:
        """Get all cached reports with blogger info"""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT ar.user_id, ar.report_mode, ar.provider, ar.model_name,
                       ar.generated_at, ar.note_covers, b.nickname
                FROM ai_reports ar
                LEFT JOIN bloggers b ON ar.user_id = b.user_id
                ORDER BY ar.generated_at DESC
            """)
            return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def clear_all() -> int:
        """Clear all AI reports from database"""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM ai_reports")
                return cursor.rowcount
        except Exception as e:
            print(f"Error clearing AI reports: {e}")
            return 0

    # Legacy methods for backward compatibility
    @staticmethod
    def get_cached_report(user_id: str, ttl_seconds: int = 3600) -> Optional[str]:
        """
        (Legacy) Get cached AI report - for backward compatibility

        New code should use get_report() instead
        """
        report = AIReportDB.get_report(user_id, report_mode="traffic")
        if not report:
            return None

        # Check TTL
        try:
            generated_at_str = report['generated_at']
            generated_at = datetime.fromisoformat(generated_at_str.replace(' ', 'T'))
            age_seconds = (datetime.utcnow() - generated_at).total_seconds()
            if age_seconds > ttl_seconds:
                return None
        except:
            pass

        return report['report_content']

    @staticmethod
    def clear_cache(user_id: Optional[str] = None) -> int:
        """(Legacy) Clear cache - for backward compatibility"""
        if user_id:
            return AIReportDB.delete_report(user_id)
        else:
            return AIReportDB.clear_all()

    @staticmethod
    def get_all_cached_reports() -> List[Dict[str, Any]]:
        """(Legacy) Get all reports - for backward compatibility"""
        return AIReportDB.get_all_reports()


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
