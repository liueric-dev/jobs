# Jobs ingestion

This repository currently contains only the job-posting ingestion pipeline.
It fetches, normalizes, deduplicates, and tracks open/closed postings in
Postgres. The previous web app, ranking/evaluation layer, and Apify actor have
been removed for redesign. Existing database rows are not deleted by this reset.

See [backend/README.md](backend/README.md) for setup and operation. Deployment
examples are in `deploy/`.

## Recovery

The previous code and documentation are available at Git tag
`archive/pre-simplification-2026-09-24`.
