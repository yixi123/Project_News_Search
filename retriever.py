import pandas as pd
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


# =========================
# Load data and embeddings
# =========================

ALL_NEWS_PATH = "/Users/sharon/Downloads/embedding_output/all_news.csv"
EMBEDDINGS_PATH = "/Users/sharon/Downloads/embedding_output/news_embeddings.npy"

all_news = pd.read_csv(ALL_NEWS_PATH)
embeddings = np.load(EMBEDDINGS_PATH)


# =========================
# Load embedding model
# =========================

model = SentenceTransformer("BAAI/bge-small-en-v1.5")


# =========================
# Retrieval function
# =========================

def get_articles_from_query(user_query, top_k=10):
    """
    Retrieve timeline-aware news articles based on a user query.

    The function:
    1. Encodes the user query
    2. Computes similarity with saved news embeddings
    3. Selects top relevant articles
    4. Diversifies results across years
    """

    query = (
        "Represent this sentence for searching relevant passages: "
        + user_query
    )

    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True
    )

    scores = cosine_similarity(
        query_embedding,
        embeddings
    )[0]

    temp_df = all_news.copy()
    temp_df["score"] = scores

    temp_df["year"] = pd.to_datetime(
        temp_df["date"],
        errors="coerce"
    ).dt.year

    temp_df = temp_df.sort_values(
        "score",
        ascending=False
    ).head(200)

    results = []

    for year in sorted(temp_df["year"].dropna().unique()):
        yearly_news = (
            temp_df[temp_df["year"] == year]
            .sort_values("score", ascending=False)
            .head(2)
        )

        results.append(yearly_news)

    if len(results) == 0:
        return []

    results_df = pd.concat(results)

    results_df = results_df.sort_values("date")

    articles = []

    for _, row in results_df.iterrows():
        articles.append({
            "date": row["date"],
            "title": row["title"],
            "description": row["description"],
            "url": row["url"]
        })

    return articles[:top_k]


# =========================
# Test
# =========================

if __name__ == "__main__":
    results = get_articles_from_query(
        "covid",
        top_k=10
    )

    for article in results:
        print(article)