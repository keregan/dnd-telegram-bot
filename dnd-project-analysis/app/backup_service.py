from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


logger = logging.getLogger(__name__)


def _create_backup(database_path: str, backup_dir: str, retention_days: int) -> Path:
    source_path = Path(database_path)
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S')
    target_path = target_dir / f'dnd_bot_{stamp}.sqlite3'

    with sqlite3.connect(source_path) as source, sqlite3.connect(target_path) as target:
        source.backup(target)
        result = target.execute('PRAGMA integrity_check').fetchone()
        if not result or result[0] != 'ok':
            raise RuntimeError(f'Backup integrity check failed: {result}')
        target.execute('PRAGMA journal_mode = DELETE')

    for suffix in ('-wal', '-shm'):
        target_path.with_name(target_path.name + suffix).unlink(missing_ok=True)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
    for old_backup in target_dir.glob('dnd_bot_*.sqlite3'):
        if old_backup == target_path:
            continue
        modified = datetime.fromtimestamp(old_backup.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            old_backup.unlink()
            for suffix in ('-wal', '-shm'):
                old_backup.with_name(old_backup.name + suffix).unlink(missing_ok=True)
    return target_path


async def run_backup_once(database_path: str, backup_dir: str, retention_days: int) -> Path:
    return await asyncio.to_thread(_create_backup, database_path, backup_dir, retention_days)


async def backup_loop(
    database_path: str,
    backup_dir: str,
    interval_hours: int,
    retention_days: int,
) -> None:
    while True:
        try:
            path = await run_backup_once(database_path, backup_dir, retention_days)
            logger.info('Database backup created: %s', path)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Database backup failed')
        await asyncio.sleep(max(1, interval_hours) * 3600)
