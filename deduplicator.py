from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import re

# ─── LOAD MODEL ONCE (SAFE INIT) ─────────────────────────
model = SentenceTransformer("all-MiniLM-L6-v2")


# ─── CLEAN TEXT ───────────────────────────────────────────

def clean_text(text):
    text = text or ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ─── SAFE GET ─────────────────────────────────────────────

def safe_get(article, key):
    return article.get(key, "") or ""


# ─── MAIN DEDUP FUNCTION ──────────────────────────────────

def deduplicate(articles, threshold=0.85):

    if not articles:
        return []

    # Step 1: Build clean texts
    texts = []
    valid_articles = []

    for a in articles:
        title = clean_text(safe_get(a, "title"))
        summary = clean_text(safe_get(a, "summary"))

        if not title:
            continue

        text = (title + " " + summary).strip()
        texts.append(text)
        valid_articles.append(a)

    if not texts:
        return []

    # Step 2: Embeddings
    embeddings = model.encode(texts, show_progress_bar=False)
    sim_matrix = cosine_similarity(embeddings)

    visited = set()
    merged = []

    # Step 3: Improved clustering
    for i in range(len(valid_articles)):

        if i in visited:
            continue

        cluster = []

        for j in range(len(valid_articles)):
            if j not in visited and sim_matrix[i][j] >= threshold:
                cluster.append(j)

        if not cluster:
            continue

        visited.update(cluster)

        # Step 4: Pick BEST article in cluster (highest trust_score, then longest text)
        best_idx = max(cluster, key=lambda k: (
            valid_articles[k].get("trust_score", 0),
            len(texts[k]),
        ))

        best = dict(valid_articles[best_idx])  # COPY (important fix)

        # Step 5: Merge sources safely
        sources = list(set(
            valid_articles[k].get("url", "")
            for k in cluster
            if valid_articles[k].get("url")
        ))

        best["sources"] = sources

        merged.append(best)

    print(f"After dedup: {len(merged)} unique stories")

    return merged