"""
Database management
"""
import datetime
import logging
import os
import sqlite3

from constants import DATABASE_NAME


class DatabaseManager:
    def __init__(self, current_dir):
        self.db_path = os.path.join(current_dir, DATABASE_NAME)
        self.conn = None
        self.cursor = None
        self._connect()
        self._create_table()
        self._add_is_pinned_column()

    def _connect(self):
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.cursor = self.conn.cursor()
            logging.info(f"DatabaseManager: Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error connecting to database {self.db_path}: {e}")

    def _create_table(self):
        try:
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS clips (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_pinned BOOLEAN DEFAULT FALSE
                )
            """)
            self.conn.commit()
            logging.info("DatabaseManager: Table 'clips' ensured.")
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error creating table 'clips': {e}")

    def _add_is_pinned_column(self):
        try:
            self.cursor.execute("SELECT is_pinned FROM clips LIMIT 1")
            logging.debug("DatabaseManager: 'is_pinned' column already exists.")
        except sqlite3.OperationalError:
            try:
                self.cursor.execute("ALTER TABLE clips ADD COLUMN is_pinned BOOLEAN DEFAULT FALSE")
                self.conn.commit()
                logging.info("DatabaseManager: Added 'is_pinned' column to 'clips' table.")
            except sqlite3.Error as e:
                logging.error(f"DatabaseManager: Error adding 'is_pinned' column: {e}")

    def add_clip(self, clip_type, content, is_pinned=False):
        try:
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute(
                "INSERT INTO clips (type, content, timestamp, is_pinned) VALUES (?, ?, ?, ?)",
                (clip_type, content, current_time, is_pinned)
            )
            self.conn.commit()
            new_id = self.cursor.lastrowid
            logging.info(f"DatabaseManager: Clip added with ID: {new_id}, Type: {clip_type}")
            return new_id
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error adding clip (Type: {clip_type}, Content: {content[:100]}...): {e}")
            return None

    def update_clip_content(self, clip_id, new_content):
        try:
            self.cursor.execute("UPDATE clips SET content = ? WHERE id = ?", (new_content, clip_id))
            self.conn.commit()
            logging.info(f"DatabaseManager: Clip ID {clip_id} content updated successfully.")
            return True
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error updating clip ID {clip_id} content: {e}")
            return False

    def update_clip_type(self, clip_id, new_type):
        try:
            self.cursor.execute("UPDATE clips SET type = ? WHERE id = ?", (new_type, clip_id))
            self.conn.commit()
            logging.info(f"DatabaseManager: Clip ID {clip_id} type updated to {new_type} successfully.")
            return True
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error updating clip ID {clip_id} type: {e}")
            return False

    def get_all_clips(self):
        try:
            self.cursor.execute("SELECT id, type, content, is_pinned FROM clips ORDER BY is_pinned DESC, timestamp DESC")
            clips = self.cursor.fetchall()
            logging.debug(f"DatabaseManager: Fetched {len(clips)} clips.")
            return clips
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error fetching all clips: {e}")
            return []

    def delete_clip(self, clip_id):
        try:
            self.cursor.execute("DELETE FROM clips WHERE id = ?", (clip_id,))
            self.conn.commit()
            if self.cursor.rowcount > 0:
                logging.info(f"DatabaseManager: Clip ID {clip_id} deleted successfully.")
                return True
            else:
                logging.warning(f"DatabaseManager: Clip ID {clip_id} not found for deletion.")
                return False
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error deleting clip ID {clip_id}: {e}")
            return False

    def delete_all_clips(self):
        try:
            self.cursor.execute("DELETE FROM clips WHERE is_pinned = FALSE")
            self.conn.commit()
            deleted_count = self.cursor.rowcount
            if deleted_count > 0:
                self.conn.execute("VACUUM")
                logging.info(f"DatabaseManager: Deleted {deleted_count} unpinned clips and vacuumed database.")
            else:
                logging.info(f"DatabaseManager: Deleted {deleted_count} unpinned clips.")
            return deleted_count > 0
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error deleting all unpinned clips: {e}")
            return False

    def delete_old_clips(self, days):
        try:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=days)
            cutoff_date_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute("DELETE FROM clips WHERE timestamp < ? AND is_pinned = FALSE", (cutoff_date_str,))
            deleted_count = self.cursor.rowcount
            self.conn.commit()
            if deleted_count > 0:
                self.conn.execute("VACUUM")
                logging.info(f"DatabaseManager: Deleted {deleted_count} old unpinned clips and vacuumed database.")
            else:
                logging.info(f"DatabaseManager: Deleted {deleted_count} old unpinned clips.")
            return deleted_count
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error deleting old clips: {e}")
            return 0

    def toggle_pin_status(self, clip_id, is_pinned):
        try:
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute(
                "UPDATE clips SET is_pinned = ?, timestamp = ? WHERE id = ?",
                (is_pinned, current_time, clip_id)
            )
            self.conn.commit()
            if self.cursor.rowcount > 0:
                logging.info(f"DatabaseManager: Clip ID {clip_id} pin status toggled to {is_pinned}.")
                return True
            else:
                logging.warning(f"DatabaseManager: Clip ID {clip_id} not found for pin toggle.")
                return False
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error toggling pin status for clip ID {clip_id}: {e}")
            return False

    def update_clip_timestamp(self, clip_id):
        try:
            current_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.cursor.execute(
                "UPDATE clips SET timestamp = ? WHERE id = ?",
                (current_time, clip_id)
            )
            self.conn.commit()
            if self.cursor.rowcount > 0:
                logging.info(f"DatabaseManager: Clip ID {clip_id} timestamp updated successfully.")
                return True
            else:
                logging.warning(f"DatabaseManager: Clip ID {clip_id} not found for timestamp update.")
                return False
        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error updating timestamp for clip ID {clip_id}: {e}")
            return False

    def enforce_max_history(self, max_count):
        deleted_clip_ids = []
        failed_attempts = 0
        max_failed_attempts = 10
        try:
            self.cursor.execute("SELECT COUNT(*) FROM clips WHERE is_pinned = FALSE")
            unpinned_clips_count = self.cursor.fetchone()[0]
            self.cursor.execute("SELECT COUNT(*) FROM clips WHERE is_pinned = TRUE")
            pinned_clips_count = self.cursor.fetchone()[0]
            effective_max_unpinned_count = max(0, max_count - pinned_clips_count)

            if unpinned_clips_count <= effective_max_unpinned_count:
                return deleted_clip_ids
            num_to_delete = unpinned_clips_count - effective_max_unpinned_count
            logging.info(f"DatabaseManager: Unpinned clips ({unpinned_clips_count}) exceeds effective max ({effective_max_unpinned_count}). Will attempt to delete {num_to_delete} oldest unpinned clips.")
            while len(deleted_clip_ids) < num_to_delete and failed_attempts < max_failed_attempts:
                self.cursor.execute(
                    "SELECT id FROM clips WHERE is_pinned = FALSE ORDER BY timestamp ASC LIMIT 1"
                )
                oldest_unpinned_clip = self.cursor.fetchone()
                if oldest_unpinned_clip:
                    clip_id_to_delete = oldest_unpinned_clip[0]
                    if self.delete_clip(clip_id_to_delete):
                        deleted_clip_ids.append(clip_id_to_delete)
                        failed_attempts = 0
                    else:
                        failed_attempts += 1
                        logging.warning(f"DatabaseManager: Failed to delete oldest unpinned clip ID {clip_id_to_delete} (attempt {failed_attempts}/{max_failed_attempts}). Trying next...")
                        continue
                else:
                    logging.info("DatabaseManager: No more unpinned clips to delete to enforce max history.")
                    break
            if deleted_clip_ids:
                self.conn.execute("VACUUM")
                logging.info(f"DatabaseManager: Enforced max history. Deleted {len(deleted_clip_ids)} clip(s), database vacuumed.")
            if failed_attempts >= max_failed_attempts:
                logging.warning(f"DatabaseManager: Stopped enforcing max history after {max_failed_attempts} consecutive failures.")
            return deleted_clip_ids

        except sqlite3.Error as e:
            logging.error(f"DatabaseManager: Error enforcing max history: {e}")
            return []

    def close(self):
        if self.conn:
            try:
                self.conn.close()
                logging.info("DatabaseManager: Database connection closed.")
            except sqlite3.Error as e:
                logging.warning(f"DatabaseManager: Error closing database connection: {e}")
