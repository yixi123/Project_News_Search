import numpy as np
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModelForSequenceClassification, AutoTokenizer


# =========================
# Config
# =========================

ALL_NEWS_PATH = "all_news/all_news.csv"
EMBEDDINGS_PATH = "all_news/news_embeddings.npy"

EMBEDDING_MODEL_NAME = "BAAI/bge-small-en-v1.5"
RERANKER_MODEL_NAME = "BAAI/bge-reranker-base"
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


# =========================
# Load data, embeddings, and models immediately
# =========================

all_news = pd.read_csv(ALL_NEWS_PATH)
embeddings = np.load(EMBEDDINGS_PATH)

embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
reranker_tokenizer = AutoTokenizer.from_pretrained(RERANKER_MODEL_NAME)
reranker_model = AutoModelForSequenceClassification.from_pretrained(RERANKER_MODEL_NAME)
reranker_model.eval()


# =========================
# Helpers
# =========================

def _build_passage(row):
    title = "" if pd.isna(row.get("title")) else str(row.get("title"))
    description = "" if pd.isna(row.get("description")) else str(row.get("description"))
    return f"{title}. {description}".strip()


def _add_year_column(df):
    df = df.copy()
    df["year"] = pd.to_datetime(df["date"], errors="coerce").dt.year
    return df


def _vector_candidates(user_query, candidate_k):
    query_embedding = embedding_model.encode(
        [QUERY_INSTRUCTION + user_query],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    scores = np.dot(embeddings, query_embedding[0])

    candidate_k = min(candidate_k, len(all_news))
    if candidate_k >= len(scores):
        top_indices = np.argsort(scores)[::-1]
    else:
        top_indices = np.argpartition(scores, -candidate_k)[-candidate_k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

    candidates = all_news.iloc[top_indices].copy()
    candidates["embedding_score"] = scores[top_indices]
    candidates["candidate_rank"] = np.arange(1, len(candidates) + 1)
    return _add_year_column(candidates)


def _rerank_candidates(user_query, candidates, batch_size=16):
    if len(candidates) == 0:
        candidates = candidates.copy()
        candidates["rerank_score"] = []
        return candidates

    passages = [_build_passage(row) for _, row in candidates.iterrows()]
    pairs = [[user_query, passage] for passage in passages]

    scores = []
    with torch.no_grad():
        for start in range(0, len(pairs), batch_size):
            batch = pairs[start:start + batch_size]
            inputs = reranker_tokenizer(
                batch,
                padding=True,
                truncation=True,
                return_tensors="pt",
                max_length=512,
            )
            batch_scores = reranker_model(**inputs, return_dict=True).logits.view(-1).float()
            scores.extend(batch_scores.cpu().numpy().tolist())

    reranked = candidates.copy()
    reranked["rerank_score"] = scores
    return reranked.sort_values("rerank_score", ascending=False)


def _timeline_diversify(candidates, top_k):
    candidates = candidates.dropna(subset=["year"])
    if len(candidates) == 0:
        return candidates

    number_of_years = max(1, candidates["year"].nunique())
    per_year = max(1, int(np.ceil(top_k / number_of_years)))

    yearly_results = []
    for _, yearly_news in candidates.groupby("year", sort=True):
        yearly_results.append(
            yearly_news.sort_values("rerank_score", ascending=False).head(per_year)
        )

    results = pd.concat(yearly_results).sort_values(
        ["rerank_score", "embedding_score"],
        ascending=False,
    )

    if len(results) < top_k:
        used_urls = set(results["url"].dropna().astype(str))
        extra = candidates[~candidates["url"].astype(str).isin(used_urls)]
        results = pd.concat([results, extra]).drop_duplicates(subset=["url"])

    return results.head(top_k).sort_values("date")


def _articles_from_df(results_df):
    articles = []
    for _, row in results_df.iterrows():
        articles.append({
            "date": row["date"],
            "title": row["title"],
            "description": row["description"],
            "url": row["url"],
            "score": float(row.get("rerank_score", 0.0)),
            "embedding_score": float(row.get("embedding_score", 0.0)),
            "rerank_score": float(row.get("rerank_score", 0.0)),
        })
    return articles


# =========================
# Retrieval functions
# =========================

def get_articles_from_query(
    user_query,
    top_k=10,
    candidate_k=100,
    use_reranker=True,
    rerank_batch_size=16,
):
    """
    Retrieve timeline-aware articles with optional BGE reranking.

    Pipeline:
    1. Embed the user query with BGE-small-en-v1.5
    2. Retrieve a larger candidate pool by cosine similarity
    3. Re-rank candidate query/article pairs with bge-reranker-base
    4. Select year-diverse articles and sort final output chronologically
    """

    candidates = _vector_candidates(user_query, candidate_k=max(candidate_k, top_k))

    if use_reranker:
        candidates = _rerank_candidates(
            user_query,
            candidates,
            batch_size=rerank_batch_size,
        )
    else:
        candidates = candidates.copy()
        candidates["rerank_score"] = candidates["embedding_score"]
        candidates = candidates.sort_values("embedding_score", ascending=False)

    results_df = _timeline_diversify(candidates, top_k)
    return _articles_from_df(results_df)


def compare_retrieval_with_and_without_rerank(user_query, top_k=10, candidate_k=50):
    """Return side-by-side retrieval results for notebook evaluation."""
    without_rerank = get_articles_from_query(
        user_query,
        top_k=top_k,
        candidate_k=candidate_k,
        use_reranker=False,
    )
    with_rerank = get_articles_from_query(
        user_query,
        top_k=top_k,
        candidate_k=candidate_k,
        use_reranker=True,
    )
    return (
        pd.DataFrame(without_rerank),
        pd.DataFrame(with_rerank),
    )


# =========================
# Test
# =========================

if __name__ == "__main__":
    query = "Covid-19 pandemic impact in healthcare"
    results = get_articles_from_query(query, top_k=10, candidate_k=50)
    results_df = pd.DataFrame(results)

    print(f"Retrieved {len(results_df)} articles for query: {query}")
    if not results_df.empty:
        results_df["year"] = pd.to_datetime(results_df["date"], errors="coerce").dt.year
        print(results_df[["date", "title", "embedding_score", "rerank_score"]])
        print("Years:", sorted(results_df["year"].dropna().unique()))
