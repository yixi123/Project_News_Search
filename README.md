# NewsTrace

NewsTrace is a news retrieval and timeline-generation project. It searches a preprocessed news corpus with dense embeddings, optionally reranks the candidates, selects a timeline-diverse set of articles, and uses an LLM to generate a chronological response.

## Features

- Semantic news retrieval with `BAAI/bge-small-en-v1.5`
- Cross-encoder reranking with `BAAI/bge-reranker-base`
- Year-aware result diversification and chronological sorting
- Flask API with server-sent event streaming for long-running queries
- Query validation and timeline generation through the configured LLM provider
- Feedback and action logging for the web application
- Jupyter notebooks for dataset preparation and embedding generation

## Repository Layout

```text
.
├── all_news/
│   ├── all_news.csv          # Retrieval corpus
│   └── news_embeddings.npy   # Precomputed corpus embeddings
├── dataset/                  # Source datasets and intermediate data
├── web/
│   ├── app.py                # Flask application
│   ├── templates/            # Flask HTML templates
│   └── static/                # Frontend assets
├── retriever.py              # Embedding retrieval and reranking
├── GDELT_collector.py        # GDELT data collection utility
├── prompt.py                 # LLM prompt construction
├── LLM_DeepSeek.py           # DeepSeek client and streaming pipeline
├── GeneratingEmbedding.ipynb # Embedding generation workflow
├── ReformatDataset.ipynb     # Dataset preparation workflow
└── requirements.txt          # Python dependencies
```

## Requirements

- Python 3.10 or newer
- A working LLM API key for the provider used by the application
- The prepared files `all_news/all_news.csv` and `all_news/news_embeddings.npy`
- Internet access on first run so Hugging Face can download the embedding and reranker models

The checked-in `requirements.txt` is UTF-16 encoded. Install it with pip as usual; if your tooling cannot read it, convert it to UTF-8 before installation.

## Setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On macOS or Linux, activate the environment with:

```bash
source .venv/bin/activate
```

### API Keys

`config.py` is intentionally ignored by Git because it contains local credentials. Create or update it with the API keys required by the LLM and dataset integrations. For DeepSeek, `DEEPSEEK_API_KEY` can be supplied as an environment variable and takes precedence over the value in `config.py`.

Do not commit API keys. Rotate any key that has been exposed outside the intended local environment.

## Run the Web Application

Start the Flask backend from the repository root:

```powershell
python web/app.py
```

Open <http://127.0.0.1:5000> in a browser. The backend serves the frontend and creates `logs_action/`, `logs_deepseek/`, and `feedback/` as needed.

Check that the service is available:

```powershell
Invoke-WebRequest http://127.0.0.1:5000/api/health
```

The main search endpoint streams progress and results as server-sent events:

```text
GET /api/news?query=Covid-19%20pandemic%20impact%20in%20healthcare
```

Feedback is submitted as JSON to `POST /api/feedback` with a non-empty `message` field.

## Use the Retriever Directly

```powershell
python retriever.py
```

Or import it from Python:

```python
from retriever import get_articles_from_query

articles = get_articles_from_query(
    "Covid-19 pandemic impact in healthcare",
    top_k=10,
    candidate_k=50,
    use_reranker=True,
)
```

The first import loads the news corpus, embeddings, and Hugging Face models, so startup may take some time.

## Data Preparation

The notebooks describe the project-specific data workflow:

1. Download or collect source data with `download_dataset.ipynb` or `GDELT_collector.py`.
2. Reformat and combine datasets with `ReformatDataset.ipynb`.
3. Generate `all_news/news_embeddings.npy` with `GeneratingEmbedding.ipynb`.
4. Evaluate retrieval and reranking with `RerankRetrievalTest.ipynb`.

The GDELT collector supports date ranges, worker counts, domain filters, and output paths. Run `python GDELT_collector.py --help` to see its command-line options.

## Notes

- Queries sent to the web API must be in English and no longer than 100 characters.
- Retrieval paths are relative to the repository root, so start the application from this directory.
- The current web server is intended for local development. Review authentication, CORS, logging, and secret management before deploying it publicly.
