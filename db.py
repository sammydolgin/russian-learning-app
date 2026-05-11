import sqlite3
import json
import re
import random
import os
from pathlib import Path
from datetime import date

# Use environment variable for DB path (for persistent disk on Render)
# Fall back to local data/ directory for development
DB_DIR = Path(os.getenv("DB_PATH", str(Path(__file__).parent / "data")))
DB_PATH = DB_DIR / "russian_learning.db"
CONTENT_PATH = Path(__file__).parent / "data" / "content"

UNLOCK_PASSWORD = "pumpernickel"
VISIBLE_PHASE_TYPES = ("alphabet", "words", "phrases", "phrases_reverse")


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _load_new_content(conn):
    """Pick up content files whose phase name isn't yet in the DB. Only loads visible types."""
    existing_names = {row["name"] for row in conn.execute("SELECT name FROM phases").fetchall()}

    level_max_parts = (("a0", 10), ("a1", 20), ("a2", 30))
    loaded = 0
    for level, max_parts in level_max_parts:
        for part in range(1, max_parts + 1):
            for phase_type in ("words", "phrases", "phrases_reverse"):
                fp = CONTENT_PATH / f"{level}_part{part}_{phase_type}.json"
                if not fp.exists():
                    continue
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                if data["phase"] in existing_names:
                    continue
                max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM phases").fetchone()[0]
                max_order = conn.execute("SELECT COALESCE(MAX(order_num), 0) FROM phases").fetchone()[0]
                phase_id = max_id + 1
                conn.execute(
                    "INSERT INTO phases (id, name, type, level, order_num, total_items) VALUES (?,?,?,?,?,?)",
                    (phase_id, data["phase"], phase_type, data["level"], max_order + 1, len(data["items"]))
                )
                for item in data["items"]:
                    row = conn.execute(
                        "INSERT INTO items (phase_id, prompt, answer, alt_answers, example, example_translation) VALUES (?,?,?,?,?,?)",
                        (phase_id, item["prompt"], item["answer"], json.dumps(item.get("alt_answers", [])), item.get("example"), item.get("example_translation"))
                    )
                    conn.execute("INSERT INTO progress (item_id) VALUES (?)", (row.lastrowid,))
                existing_names.add(data["phase"])
                loaded += 1
    return loaded


def _sync_existing_phase_items(conn):
    """For phases already in DB:
      - Insert items present in the content file but missing from the DB
      - Update answer/alt_answers/example/example_translation for items that already exist
    Never removes items (would lose progress)."""
    phases_by_name = {row["name"]: row["id"] for row in conn.execute("SELECT id, name FROM phases").fetchall()}

    for fp in sorted(CONTENT_PATH.glob("*.json")):
        if fp.name.startswith("."):
            continue
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or "phase" not in data or "items" not in data:
            continue
        phase_id = phases_by_name.get(data["phase"])
        if phase_id is None:
            continue
        existing = {row["prompt"]: row["id"] for row in conn.execute(
            "SELECT id, prompt FROM items WHERE phase_id=?", (phase_id,)
        ).fetchall()}
        inserted = 0
        for item in data["items"]:
            alt_json = json.dumps(item.get("alt_answers", []))
            if item["prompt"] in existing:
                conn.execute(
                    "UPDATE items SET answer=?, alt_answers=?, example=?, example_translation=? WHERE id=?",
                    (item["answer"], alt_json, item.get("example"), item.get("example_translation"),
                     existing[item["prompt"]])
                )
                continue
            row = conn.execute(
                "INSERT INTO items (phase_id, prompt, answer, alt_answers, example, example_translation) VALUES (?,?,?,?,?,?)",
                (phase_id, item["prompt"], item["answer"], alt_json,
                 item.get("example"), item.get("example_translation"))
            )
            conn.execute("INSERT INTO progress (item_id) VALUES (?)", (row.lastrowid,))
            inserted += 1
        if inserted:
            new_count = conn.execute(
                "SELECT COUNT(*) FROM items WHERE phase_id=?", (phase_id,)
            ).fetchone()[0]
            conn.execute("UPDATE phases SET total_items=? WHERE id=?", (new_count, phase_id))


def _normalize_current_phase(conn):
    """If current_phase points to a hidden type, jump to the next visible phase."""
    row = conn.execute("SELECT value FROM app_state WHERE key='current_phase_id'").fetchone()
    if not row or row["value"] == "complete":
        return
    try:
        pid = int(row["value"])
    except (TypeError, ValueError):
        return
    phase = conn.execute("SELECT order_num, type FROM phases WHERE id=?", (pid,)).fetchone()
    if not phase or phase["type"] in VISIBLE_PHASE_TYPES:
        return
    placeholders = ",".join("?" * len(VISIBLE_PHASE_TYPES))
    next_phase = conn.execute(
        f"SELECT id FROM phases WHERE order_num >= ? AND type IN ({placeholders}) "
        f"ORDER BY order_num LIMIT 1",
        (phase["order_num"], *VISIBLE_PHASE_TYPES)
    ).fetchone()
    target = next_phase["id"] if next_phase else None
    if target is not None:
        conn.execute(
            "UPDATE app_state SET value=? WHERE key='current_phase_id'",
            (str(target),)
        )


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS phases (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                level TEXT NOT NULL,
                order_num INTEGER NOT NULL,
                total_items INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase_id INTEGER NOT NULL REFERENCES phases(id),
                prompt TEXT NOT NULL,
                answer TEXT NOT NULL,
                alt_answers TEXT NOT NULL DEFAULT '[]',
                example TEXT,
                example_translation TEXT
            );
            CREATE TABLE IF NOT EXISTS answer_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase_id INTEGER NOT NULL REFERENCES phases(id),
                item_id INTEGER NOT NULL REFERENCES items(id),
                is_correct INTEGER NOT NULL,
                answered_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS progress (
                item_id INTEGER PRIMARY KEY REFERENCES items(id),
                times_seen INTEGER NOT NULL DEFAULT 0,
                times_correct INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'unseen',
                last_seen TEXT
            );
            CREATE TABLE IF NOT EXISTS quiz_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phase_id INTEGER NOT NULL REFERENCES phases(id),
                date TEXT NOT NULL,
                items_quizzed INTEGER NOT NULL,
                correct INTEGER NOT NULL,
                accuracy REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        _migrate_schema(conn)
        if conn.execute("SELECT COUNT(*) FROM phases").fetchone()[0] == 0:
            _load_content(conn)
        else:
            _load_new_content(conn)
            _sync_existing_phase_items(conn)
        _normalize_current_phase(conn)
        conn.commit()


def _migrate_schema(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(items)").fetchall()}
    if "example" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN example TEXT")
    if "example_translation" not in cols:
        conn.execute("ALTER TABLE items ADD COLUMN example_translation TEXT")


def _load_content(conn):
    with open(CONTENT_PATH / "alphabet.json", encoding="utf-8") as f:
        alphabet = json.load(f)

    for group in alphabet["groups"]:
        conn.execute(
            "INSERT INTO phases (id, name, type, level, order_num, total_items) VALUES (?,?,?,?,?,?)",
            (group["id"], group["name"], "alphabet", "alphabet", group["id"], len(group["letters"]))
        )
        for letter in group["letters"]:
            row = conn.execute(
                "INSERT INTO items (phase_id, prompt, answer, alt_answers) VALUES (?,?,?,?)",
                (group["id"], letter["letter"], letter["phonetic"], json.dumps(letter["accepted"]))
            )
            conn.execute("INSERT INTO progress (item_id) VALUES (?)", (row.lastrowid,))

    _load_new_content(conn)
    conn.execute("INSERT INTO app_state (key, value) VALUES ('current_phase_id', '1')")


def get_current_phase() -> dict | None:
    with _conn() as conn:
        row = conn.execute("SELECT value FROM app_state WHERE key='current_phase_id'").fetchone()
        if not row or row["value"] == "complete":
            return None
        phase = conn.execute("SELECT * FROM phases WHERE id=?", (int(row["value"]),)).fetchone()
        return dict(phase) if phase else None


def get_phase_stats(phase_id: int) -> dict:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT p.status, COUNT(*) as cnt
            FROM items i JOIN progress p ON p.item_id = i.id
            WHERE i.phase_id = ?
            GROUP BY p.status
            """,
            (phase_id,)
        ).fetchall()
        stats = {"mastered": 0, "review": 0, "unseen": 0}
        for r in rows:
            stats[r["status"]] = r["cnt"]
        return stats


def get_graduation_status(phase_id: int) -> dict:
    with _conn() as conn:
        phase = conn.execute("SELECT total_items FROM phases WHERE id=?", (phase_id,)).fetchone()
        if not phase:
            return {"accuracy": 0.0, "coverage": 0.0, "can_graduate": False,
                    "total_seen": 0, "covered": 0, "total_items": 0}

        total_items = phase["total_items"]
        covered = conn.execute(
            """
            SELECT COUNT(*) FROM progress p JOIN items i ON i.id = p.item_id
            WHERE i.phase_id=? AND p.times_correct > 0
            """,
            (phase_id,)
        ).fetchone()[0]

        recent = conn.execute(
            """
            SELECT is_correct FROM answer_log
            WHERE phase_id=? ORDER BY id DESC LIMIT 100
            """,
            (phase_id,)
        ).fetchall()
        total_seen = len(recent)
        total_correct = sum(r["is_correct"] for r in recent)

        accuracy = total_correct / total_seen if total_seen > 0 else 0.0
        coverage = covered / total_items if total_items > 0 else 0.0

        return {
            "accuracy": accuracy,
            "coverage": coverage,
            "can_graduate": accuracy >= 0.85 and coverage >= 0.50,
            "total_correct": total_correct,
            "total_seen": total_seen,
            "covered": covered,
            "total_items": total_items,
        }


def get_quiz_items(phase_id: int, n: int = 10) -> list[dict]:
    with _conn() as conn:
        unseen = conn.execute(
            """
            SELECT i.id, i.prompt, i.answer, i.alt_answers, i.example, i.example_translation, p.status
            FROM items i JOIN progress p ON p.item_id = i.id
            WHERE i.phase_id=? AND p.status='unseen'
            ORDER BY RANDOM() LIMIT ?
            """,
            (phase_id, n)
        ).fetchall()

        review = conn.execute(
            """
            SELECT i.id, i.prompt, i.answer, i.alt_answers, i.example, i.example_translation, p.status,
                   CAST(p.times_correct AS REAL) / NULLIF(p.times_seen, 0) AS acc

            FROM items i JOIN progress p ON p.item_id = i.id
            WHERE i.phase_id=? AND p.status='review'
            ORDER BY acc ASC NULLS FIRST, p.last_seen ASC NULLS FIRST
            LIMIT ?
            """,
            (phase_id, n)
        ).fetchall()

        # ~1/3 new, ~2/3 review; fill gaps from whichever pool has more
        unseen_target = max(1, n // 3)
        review_target = n - unseen_target
        chosen = list(unseen)[:unseen_target] + list(review)[:review_target]

        # top up if either pool was short
        if len(chosen) < n:
            used_ids = {r["id"] for r in chosen}
            extras = [r for r in list(unseen) + list(review) if r["id"] not in used_ids]
            chosen += extras[: n - len(chosen)]

        # Fall back to mastered items if nothing else available
        if len(chosen) < n:
            used_ids = {r["id"] for r in chosen}
            mastered = conn.execute(
                """
                SELECT i.id, i.prompt, i.answer, i.alt_answers, i.example, i.example_translation, p.status
                FROM items i JOIN progress p ON p.item_id = i.id
                WHERE i.phase_id=? AND p.status='mastered' AND i.id NOT IN ({})
                ORDER BY RANDOM() LIMIT ?
                """.format(",".join("?" * len(used_ids)) if used_ids else "SELECT -1"),
                (phase_id, *used_ids, n - len(chosen))
            ).fetchall()
            chosen += mastered

        random.shuffle(chosen)
        return [
            {
                "id": r["id"],
                "prompt": r["prompt"],
                "answer": r["answer"],
                "alt_answers": json.loads(r["alt_answers"]),
                "example": r["example"],
                "example_translation": r["example_translation"],
                "status": r["status"],
            }
            for r in chosen
        ]


def save_quiz_result(phase_id: int, results: list[dict]):
    if not results:
        return
    today = date.today().isoformat()
    correct_count = sum(1 for r in results if r["is_correct"])
    accuracy = correct_count / len(results)

    with _conn() as conn:
        conn.execute(
            "INSERT INTO quiz_sessions (phase_id, date, items_quizzed, correct, accuracy) VALUES (?,?,?,?,?)",
            (phase_id, today, len(results), correct_count, accuracy)
        )
        for r in results:
            conn.execute(
                "INSERT INTO answer_log (phase_id, item_id, is_correct, answered_at) VALUES (?,?,?,?)",
                (phase_id, r["item_id"], 1 if r["is_correct"] else 0, today)
            )
            prog = conn.execute(
                "SELECT times_seen, times_correct FROM progress WHERE item_id=?",
                (r["item_id"],)
            ).fetchone()
            new_seen = prog["times_seen"] + 1
            new_correct = prog["times_correct"] + (1 if r["is_correct"] else 0)
            new_status = "mastered" if new_correct >= 3 else "review"
            conn.execute(
                "UPDATE progress SET times_seen=?, times_correct=?, status=?, last_seen=? WHERE item_id=?",
                (new_seen, new_correct, new_status, today, r["item_id"])
            )
        conn.commit()


def set_current_phase(phase_id: int):
    """Set the current phase to any phase by ID."""
    with _conn() as conn:
        conn.execute(
            "UPDATE app_state SET value=? WHERE key='current_phase_id'",
            (str(phase_id),)
        )
        conn.commit()


def is_phase_locked(phase_id: int) -> bool:
    """Locked unless the previous VISIBLE phase is completed, or this phase was individually unlocked."""
    if _is_phase_individually_unlocked(phase_id):
        return False

    placeholders = ",".join("?" * len(VISIBLE_PHASE_TYPES))
    with _conn() as conn:
        phase = conn.execute("SELECT order_num FROM phases WHERE id=?", (phase_id,)).fetchone()
        if not phase:
            return True

        prev_phase = conn.execute(
            f"SELECT completed FROM phases "
            f"WHERE order_num < ? AND type IN ({placeholders}) "
            f"ORDER BY order_num DESC LIMIT 1",
            (phase["order_num"], *VISIBLE_PHASE_TYPES)
        ).fetchone()

        if not prev_phase:
            return False
        return not prev_phase["completed"]


def _is_phase_individually_unlocked(phase_id: int) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT value FROM app_state WHERE key=?",
            (f"unlocked_phase_{phase_id}",)
        ).fetchone()
        return bool(row and row["value"] == "1")


def unlock_phase(phase_id: int, password: str) -> bool:
    """Unlock a single phase if password is correct."""
    if password != UNLOCK_PASSWORD:
        return False
    key = f"unlocked_phase_{phase_id}"
    with _conn() as conn:
        existing = conn.execute("SELECT value FROM app_state WHERE key=?", (key,)).fetchone()
        if existing:
            conn.execute("UPDATE app_state SET value='1' WHERE key=?", (key,))
        else:
            conn.execute("INSERT INTO app_state (key, value) VALUES (?, '1')", (key,))
        conn.commit()
    return True


def advance_phase() -> bool:
    current = get_current_phase()
    if not current:
        return False
    placeholders = ",".join("?" * len(VISIBLE_PHASE_TYPES))
    with _conn() as conn:
        conn.execute("UPDATE phases SET completed=1 WHERE id=?", (current["id"],))
        next_phase = conn.execute(
            f"SELECT id FROM phases "
            f"WHERE order_num > ? AND type IN ({placeholders}) "
            f"ORDER BY order_num LIMIT 1",
            (current["order_num"], *VISIBLE_PHASE_TYPES)
        ).fetchone()
        if next_phase:
            conn.execute(
                "UPDATE app_state SET value=? WHERE key='current_phase_id'",
                (str(next_phase["id"]),)
            )
        else:
            conn.execute(
                "UPDATE app_state SET value='complete' WHERE key='current_phase_id'"
            )
        conn.commit()
    return next_phase is not None


def get_phase_items_progress(phase_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            """
            SELECT i.prompt, i.answer, p.times_seen, p.times_correct, p.status,
                   CASE WHEN p.times_seen > 0
                        THEN CAST(p.times_correct AS REAL) / p.times_seen
                        ELSE NULL END AS accuracy
            FROM items i JOIN progress p ON p.item_id = i.id
            WHERE i.phase_id = ?
            ORDER BY i.id
            """,
            (phase_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_items_progress(item_ids: list[int]) -> dict:
    if not item_ids:
        return {}
    with _conn() as conn:
        rows = conn.execute(
            f"""
            SELECT item_id, times_seen, times_correct,
                   CASE WHEN times_seen > 0
                        THEN CAST(times_correct AS REAL) / times_seen
                        ELSE NULL END AS accuracy
            FROM progress
            WHERE item_id IN ({','.join('?' * len(item_ids))})
            """,
            item_ids
        ).fetchall()
        return {r["item_id"]: dict(r) for r in rows}


def get_all_phases() -> list[dict]:
    with _conn() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM phases ORDER BY order_num").fetchall()]


def get_quiz_history(phase_id: int = None, limit: int = 20) -> list[dict]:
    with _conn() as conn:
        if phase_id:
            rows = conn.execute(
                """
                SELECT qs.*, ph.name AS phase_name FROM quiz_sessions qs
                JOIN phases ph ON ph.id = qs.phase_id
                WHERE qs.phase_id=? ORDER BY qs.id DESC LIMIT ?
                """,
                (phase_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT qs.*, ph.name AS phase_name FROM quiz_sessions qs
                JOIN phases ph ON ph.id = qs.phase_id
                ORDER BY qs.id DESC LIMIT ?
                """,
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def migrate_from_markdown(md_path: str):
    """One-time migration of progress from Russian-Learning.md."""
    with open(md_path, encoding="utf-8") as f:
        content = f.read()

    word_re = re.compile(
        r'\|\s*([^\|]+?)\s*\|\s*[^\|]+?\s*\|\s*([✓↻○])\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d\-]+|-)\s*\|'
    )
    status_map = {"✓": "mastered", "↻": "review", "○": "unseen"}

    with _conn() as conn:
        a0_phase = conn.execute(
            "SELECT id FROM phases WHERE level='A0' AND type='words'"
        ).fetchone()
        if not a0_phase:
            print("A0 words phase not found — run init_db() first.")
            return

        migrated = 0
        for m in word_re.finditer(content):
            prompt = m.group(1).strip()
            status = status_map.get(m.group(2).strip(), "unseen")
            times_seen = int(m.group(3))
            times_correct = int(m.group(4))
            last_seen = m.group(5).strip() if m.group(5).strip() != "-" else None

            item = conn.execute(
                "SELECT id FROM items WHERE phase_id=? AND prompt=?",
                (a0_phase["id"], prompt)
            ).fetchone()
            if item:
                conn.execute(
                    "UPDATE progress SET times_seen=?, times_correct=?, status=?, last_seen=? WHERE item_id=?",
                    (times_seen, times_correct, status, last_seen, item["id"])
                )
                migrated += 1

        # Migrate quiz history
        hist_re = re.compile(r'\|\s*([\d\-]+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*([\d.]+)%')
        for m in hist_re.finditer(content):
            conn.execute(
                "INSERT INTO quiz_sessions (phase_id, date, items_quizzed, correct, accuracy) VALUES (?,?,?,?,?)",
                (a0_phase["id"], m.group(1), int(m.group(2)), int(m.group(3)), float(m.group(4)) / 100)
            )

        conn.commit()
    print(f"Migrated {migrated} word(s).")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--migrate":
        md = sys.argv[2] if len(sys.argv) > 2 else "Russian-Learning.md"
        migrate_from_markdown(md)
    else:
        init_db()
        print("DB initialized.")
