"""Database backup and restore utilities for data protection."""
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from config.settings import settings


class DatabaseBackup:
    """
    Automated database backup system.

    Features:
    - Timestamped backups before migrations
    - Restore from backup on failure
    - Backup retention management
    - Support for SQLite and PostgreSQL
    """

    def __init__(self, backup_dir: Optional[str] = None):
        """
        Initialize backup system.

        Args:
            backup_dir: Directory for backups (default: project_root/backups)
        """
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            # Default to project root/backups
            project_root = Path(__file__).parent.parent.parent
            self.backup_dir = project_root / "backups"

        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def backup_before_migration(self, label: str = "migration") -> str:
        """
        Create timestamped backup before schema changes.

        Args:
            label: Label for the backup (e.g., "migration", "pre_deploy")

        Returns:
            Path to the backup file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_url = settings.database_url

        if db_url.startswith("sqlite"):
            return self._backup_sqlite(timestamp, label)
        elif db_url.startswith("postgresql"):
            return self._backup_postgresql(timestamp, label)
        else:
            raise ValueError(f"Unsupported database type: {db_url}")

    def _backup_sqlite(self, timestamp: str, label: str) -> str:
        """Backup SQLite database by copying the file."""
        # Extract database path from URL
        db_url = settings.database_url
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
        else:
            db_path = "job_radar.db"

        if not Path(db_path).exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")

        backup_filename = f"db_backup_{label}_{timestamp}.db"
        backup_path = self.backup_dir / backup_filename

        shutil.copy2(db_path, backup_path)
        print(f"SQLite backup created: {backup_path}")

        return str(backup_path)

    def _backup_postgresql(self, timestamp: str, label: str) -> str:
        """Backup PostgreSQL database using pg_dump."""
        backup_filename = f"db_backup_{label}_{timestamp}.sql"
        backup_path = self.backup_dir / backup_filename

        db_url = settings.database_url

        try:
            result = subprocess.run(
                ["pg_dump", "-Fc", "-f", str(backup_path), db_url],
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"PostgreSQL backup created: {backup_path}")
            return str(backup_path)

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"PostgreSQL backup failed: {e.stderr}")
        except FileNotFoundError:
            raise RuntimeError("pg_dump not found. Install PostgreSQL client tools.")

    def restore_from_backup(self, backup_path: str) -> None:
        """
        Restore database from backup.

        Args:
            backup_path: Path to the backup file
        """
        if not Path(backup_path).exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        db_url = settings.database_url

        if db_url.startswith("sqlite"):
            self._restore_sqlite(backup_path)
        elif db_url.startswith("postgresql"):
            self._restore_postgresql(backup_path)
        else:
            raise ValueError(f"Unsupported database type: {db_url}")

    def _restore_sqlite(self, backup_path: str) -> None:
        """Restore SQLite database by copying the backup file."""
        db_url = settings.database_url
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
        else:
            db_path = "job_radar.db"

        # Create a backup of current state before restoring
        if Path(db_path).exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pre_restore_backup = self.backup_dir / f"pre_restore_{timestamp}.db"
            shutil.copy2(db_path, pre_restore_backup)
            print(f"Pre-restore backup created: {pre_restore_backup}")

        shutil.copy2(backup_path, db_path)
        print(f"SQLite database restored from: {backup_path}")

    def _restore_postgresql(self, backup_path: str) -> None:
        """Restore PostgreSQL database using pg_restore."""
        db_url = settings.database_url

        try:
            # Drop and recreate database
            result = subprocess.run(
                ["pg_restore", "-d", db_url, "-c", str(backup_path)],
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"PostgreSQL database restored from: {backup_path}")

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"PostgreSQL restore failed: {e.stderr}")

    def list_backups(self) -> list[dict]:
        """
        List all available backups.

        Returns:
            List of backup info dicts with path, timestamp, and size
        """
        backups = []

        for file_path in self.backup_dir.glob("db_backup_*"):
            stat = file_path.stat()
            backups.append({
                "path": str(file_path),
                "filename": file_path.name,
                "created": datetime.fromtimestamp(stat.st_mtime),
                "size_mb": stat.st_size / (1024 * 1024),
            })

        # Sort by creation time, newest first
        backups.sort(key=lambda x: x["created"], reverse=True)
        return backups

    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """
        Remove old backups, keeping the most recent ones.

        Args:
            keep_count: Number of backups to keep

        Returns:
            Number of backups deleted
        """
        backups = self.list_backups()

        if len(backups) <= keep_count:
            return 0

        to_delete = backups[keep_count:]
        deleted_count = 0

        for backup in to_delete:
            try:
                Path(backup["path"]).unlink()
                deleted_count += 1
                print(f"Deleted old backup: {backup['filename']}")
            except OSError as e:
                print(f"Failed to delete {backup['filename']}: {e}")

        return deleted_count

    def get_latest_backup(self) -> Optional[str]:
        """
        Get the path to the most recent backup.

        Returns:
            Path to latest backup, or None if no backups exist
        """
        backups = self.list_backups()
        if backups:
            return backups[0]["path"]
        return None


def backup_database(label: str = "manual") -> str:
    """
    Convenience function to create a database backup.

    Args:
        label: Label for the backup

    Returns:
        Path to the backup file
    """
    backup = DatabaseBackup()
    return backup.backup_before_migration(label)


def restore_database(backup_path: str) -> None:
    """
    Convenience function to restore a database from backup.

    Args:
        backup_path: Path to the backup file
    """
    backup = DatabaseBackup()
    backup.restore_from_backup(backup_path)
