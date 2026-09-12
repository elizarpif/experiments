# Experiments

A repo for experiments.

### Folder Structure

```
experiments/
├── database-replication
└── rate-limiter
...
```
## Projects

### embedding

Daily news aggregator (telegram bot)

- embeddings (dense and sparse) for selecting similar news
- filter by time interval (5h)
- additional level of cross-encoder NLI for detecting contradictions
- short summary generation by Ollama

### reader

a web app on Python (FastAPI) for language learning (English, Spanish). The purpose is to paste the text from the source and let Gemini (or any LLM) to select the difficult words and phrases.

### database-replication

Testing CAP-theorem scenarios for Postgres and Clickhouse

### rate-limiter

A simple realization of rate-limiter in Go with Redis and nginx.
