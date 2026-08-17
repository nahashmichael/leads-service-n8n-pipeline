# leads-service

Small FastAPI + SQLite CRUD service that stores lead state for the n8n outbound pipeline. n8n Cloud has no filesystem access, so this service is the thing n8n Cloud calls over HTTPS instead of touching a local SQLite file directly.

## Run locally

```
cd leads-service
pip install -r requirements.txt
cp .env.example .env   # only needed if you don't already have LEADS_SERVICE_API_KEY set at the repo root
uvicorn main:app --reload
```

The service reads `LEADS_SERVICE_API_KEY` from the environment (via `python-dotenv`, which walks up from this folder, so the `.env` at the repo root already works — no need to duplicate the key here unless you want a service-local override).

Try it:

```
curl http://localhost:8000/health

curl -X POST http://localhost:8000/leads \
  -H "X-API-Key: $LEADS_SERVICE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "first_name": "Ada", "source": "apollo"}'

curl "http://localhost:8000/leads?status=new" \
  -H "X-API-Key: $LEADS_SERVICE_API_KEY"
```

## Deploying so n8n Cloud can reach it

n8n Cloud runs on n8n's servers and needs a public HTTPS URL for this service — it can't reach `localhost` or your LAN. Two things matter when picking a host: **it must stay up 24/7** (not just while your laptop is on) and **it must actually persist the SQLite file across restarts/redeploys**.

Watch out for this specifically: **Render's free web service tier does not persist disks** — `leads.db` gets wiped on every restart or redeploy, silently losing all lead state. For a host that genuinely persists a small SQLite file for free (or near-free):

- **Fly.io** — free allowance covers a small persistent volume; requires a card on file for verification but shouldn't charge anything at this scale. Mount a volume at `/data` (the Dockerfile already sets `DATABASE_PATH=/data/leads.db` and declares that as a volume).
- **A small always-on VM** (e.g. Oracle Cloud's free-tier compute) if you'd rather not deal with PaaS volume quirks.

Whichever you pick, set `LEADS_SERVICE_API_KEY` as an environment variable in that host's dashboard/secrets — don't bake it into the Docker image.

## API

All endpoints except `/health` require header `X-API-Key: <LEADS_SERVICE_API_KEY>`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness check, no auth |
| POST | `/leads` | Upsert a lead by email (Phase 1 ingestion) |
| GET | `/leads?status=&min_score=` | Filtered list |
| GET | `/leads/{id}` | Single lead |
| PATCH | `/leads/{id}` | Partial update (validation/score/icebreaker/status/reply fields) |
