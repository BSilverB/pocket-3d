import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from .config import DB_PATH

_db_lock = threading.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _db_lock:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS products (
                    id TEXT PRIMARY KEY,
                    short_code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    capture_mode TEXT NOT NULL,
                    target_frames INTEGER NOT NULL,
                    frame_count INTEGER NOT NULL DEFAULT 0,
                    canvas_size INTEGER NOT NULL DEFAULT 800,
                    status TEXT NOT NULL DEFAULT 'queued',
                    progress INTEGER NOT NULL DEFAULT 0,
                    stage TEXT NOT NULL DEFAULT 'queued',
                    error_message TEXT,
                    processing_time_sec REAL NOT NULL DEFAULT 0.0,
                    package_size_mb REAL NOT NULL DEFAULT 0.0,
                    ai_engine_used TEXT NOT NULL DEFAULT 'auto',
                    thumbnail_url TEXT,
                    raw_preview_url TEXT,
                    index_json_url TEXT,
                    share_url TEXT NOT NULL,
                    viewer_url TEXT NOT NULL,
                    frames_json TEXT NOT NULL DEFAULT '[]',
                    raw_frames_json TEXT NOT NULL DEFAULT '[]',
                    hotspots_json TEXT NOT NULL DEFAULT '[]',
                    exports_json TEXT NOT NULL DEFAULT '{}',
                    metrics_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    data["frames"] = json.loads(data.pop("frames_json", "[]") or "[]")
    data["raw_frames"] = json.loads(data.pop("raw_frames_json", "[]") or "[]")
    data["hotspots"] = json.loads(data.pop("hotspots_json", "[]") or "[]")
    data["exports"] = json.loads(data.pop("exports_json", "{}") or "{}")
    data["metrics"] = json.loads(data.pop("metrics_json", "{}") or "{}")
    return data


def create_product(record: Dict[str, Any]) -> Dict[str, Any]:
    now = _utc_now()
    with _db_lock:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(
                """
                INSERT INTO products (
                    id, short_code, name, category, description, capture_mode,
                    target_frames, frame_count, canvas_size, status, progress,
                    stage, error_message, processing_time_sec, package_size_mb,
                    ai_engine_used, thumbnail_url, raw_preview_url, index_json_url,
                    share_url, viewer_url, frames_json, raw_frames_json,
                    hotspots_json, exports_json, metrics_json, created_at, updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    record["id"],
                    record["short_code"],
                    record.get("name", "Untitled Product"),
                    record.get("category", "General"),
                    record.get("description", ""),
                    record.get("capture_mode", "manual_gyro"),
                    record.get("target_frames", 36),
                    record.get("frame_count", 0),
                    record.get("canvas_size", 800),
                    record.get("status", "queued"),
                    record.get("progress", 0),
                    record.get("stage", "queued"),
                    record.get("error_message"),
                    record.get("processing_time_sec", 0.0),
                    record.get("package_size_mb", 0.0),
                    record.get("ai_engine_used", "auto"),
                    record.get("thumbnail_url"),
                    record.get("raw_preview_url"),
                    record.get("index_json_url"),
                    record["share_url"],
                    record["viewer_url"],
                    json.dumps(record.get("frames", []), ensure_ascii=False),
                    json.dumps(record.get("raw_frames", []), ensure_ascii=False),
                    json.dumps(record.get("hotspots", []), ensure_ascii=False),
                    json.dumps(record.get("exports", {}), ensure_ascii=False),
                    json.dumps(record.get("metrics", {}), ensure_ascii=False),
                    now,
                    now,
                ),
            )
            conn.commit()
            cur = conn.execute("SELECT * FROM products WHERE id = ?", (record["id"],))
            row = cur.fetchone()
            return _row_to_dict(row)
        finally:
            conn.close()


def update_product(product_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not updates:
        return get_product(product_id)

    mapped: Dict[str, Any] = {}
    for k, v in updates.items():
        if k in ("frames", "raw_frames", "hotspots", "exports", "metrics"):
            mapped[f"{k}_json"] = json.dumps(v, ensure_ascii=False)
        else:
            mapped[k] = v
    mapped["updated_at"] = _utc_now()

    cols = ", ".join(f"{col} = ?" for col in mapped.keys())
    vals = list(mapped.values()) + [product_id]

    with _db_lock:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            conn.execute(f"UPDATE products SET {cols} WHERE id = ?", vals)
            conn.commit()
            cur = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()


def get_product(product_id: str) -> Optional[Dict[str, Any]]:
    with _db_lock:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()


def get_product_by_short_code(short_code: str) -> Optional[Dict[str, Any]]:
    with _db_lock:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT * FROM products WHERE short_code = ?", (short_code,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None
        finally:
            conn.close()


def list_products() -> List[Dict[str, Any]]:
    with _db_lock:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute("SELECT * FROM products ORDER BY created_at DESC")
            rows = cur.fetchall()
            return [_row_to_dict(r) for r in rows]
        finally:
            conn.close()


def delete_product_record(product_id: str) -> bool:
    with _db_lock:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            cur = conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()
