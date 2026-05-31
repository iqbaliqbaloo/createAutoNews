import sqlite3
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from datetime import datetime, timezone, timedelta

# ─── LOAD MODEL SAFELY ─────────────────────────────
model = SentenceTransformer("all-MiniLM-L6-v2")

# Cache of (old_titles, embeddings) — populated once per process so
# title_already_posted() doesn't re-encode 200 titles on every call.
_title_emb_cache = None


# ─── INIT DB ───────────────────────────────────────

def init_db():
    conn = sqlite3.connect("state.db")
    conn.execute("PRAGMA journal_mode=WAL")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS posted (
            url_hash  TEXT,
            platform  TEXT,
            title     TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (url_hash, platform)
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_platform ON posted(platform)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_time ON posted(posted_at)")

    conn.commit()
    return conn


# ─── CHECK URL DUPLICATE ──────────────────────────

def already_posted(conn, url_hash, platform=None):
    if not url_hash:
        return False

    if platform:
        row = conn.execute(
            "SELECT 1 FROM posted WHERE url_hash=? AND platform=?",
            (url_hash, platform),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT 1 FROM posted WHERE url_hash=?",
            (url_hash,),
        ).fetchone()

    return row is not None


# ─── FAST TITLE DUPLICATE CHECK (OPTIMIZED) ───────

def title_already_posted(conn, title, threshold=0.78):
    global _title_emb_cache

    title = (title or "").strip()
    if not title:
        return False

    # Populate cache once per process — old titles don't change during a run
    if _title_emb_cache is None:
        rows = conn.execute("""
            SELECT title FROM posted
            WHERE posted_at >= datetime('now', '-3 days')
            LIMIT 200
        """).fetchall()
        old_titles = [r[0] for r in rows if r[0]]
        if old_titles:
            _title_emb_cache = (old_titles, model.encode(old_titles, show_progress_bar=False))
        else:
            _title_emb_cache = ([], None)

    old_titles, old_emb = _title_emb_cache
    if not old_titles or old_emb is None:
        return False

    new_emb = model.encode([title], show_progress_bar=False)
    sims = cosine_similarity(new_emb, old_emb)[0]
    return float(max(sims)) >= threshold


# ─── MARK POSTED ───────────────────────────────────

def mark_posted(conn, url_hash, title, platform):

    if not url_hash or not platform:
        return False

    try:
        conn.execute("""
            INSERT OR IGNORE INTO posted (url_hash, platform, title)
            VALUES (?, ?, ?)
        """, (url_hash, platform, title))

        conn.commit()
        return True

    except Exception as e:
        print(f"DB error: {e}")
        conn.rollback()
        return False


# ─── DAILY LIMIT (SAFE PKT HANDLING) ──────────────

def get_today_count(conn, platform):

    PKT = timezone(timedelta(hours=5))
    now_pkt = datetime.now(PKT)

    today_start = now_pkt.replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    today_utc = today_start.astimezone(timezone.utc)

    today_str = today_utc.strftime("%Y-%m-%d %H:%M:%S")

    row = conn.execute("""
        SELECT COUNT(*)
        FROM posted
        WHERE platform=?
        AND posted_at >= ?
    """, (platform, today_str)).fetchone()

    return row[0] if row else 0