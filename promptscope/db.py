import sqlite3
import json
import time
from pathlib import Path
from promptscope.scorer import ScoreResult

DB_PATH = Path.home() / ".promptscope" / "history.db"


def _get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT NOT NULL,
            scores TEXT NOT NULL,
            overall REAL NOT NULL,
            strengths TEXT,
            weaknesses TEXT,
            rewrite TEXT,
            created_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def save_result(result: ScoreResult) -> int:
    init_db()
    conn = _get_conn()
    cur = conn.execute(
        """INSERT INTO scores (prompt, scores, overall, strengths, weaknesses, rewrite, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            result.raw_prompt,
            json.dumps(result.scores),
            result.overall,
            json.dumps(result.strengths),
            json.dumps(result.weaknesses),
            result.rewrite_suggestion,
            int(time.time()),
        ),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def get_history(limit: int = 20) -> list:
    init_db()
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM scores ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "id": r["id"],
            "prompt": r["prompt"][:80] + "..." if len(r["prompt"]) > 80 else r["prompt"],
            "overall": r["overall"],
            "created_at": r["created_at"],
            "scores": json.loads(r["scores"]),
        })
    return results


def get_by_id(record_id: int) -> dict | None:
    init_db()
    conn = _get_conn()
    row = conn.execute("SELECT * FROM scores WHERE id = ?", (record_id,)).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row["id"],
        "prompt": row["prompt"],
        "overall": row["overall"],
        "scores": json.loads(row["scores"]),
        "strengths": json.loads(row["strengths"]),
        "weaknesses": json.loads(row["weaknesses"]),
        "rewrite": row["rewrite"],
        "created_at": row["created_at"],
    }


def delete_record(record_id: int) -> bool:
    init_db()
    conn = _get_conn()
    cur = conn.execute("DELETE FROM scores WHERE id = ?", (record_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted
