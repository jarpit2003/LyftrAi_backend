# Webhook Message Service

A FastAPI service that accepts signed webhook messages, stores them in SQLite, and exposes message querying, analytics, and Prometheus metrics.

## How to run

### Docker (recommended)

1. Set the required environment variable:

```bash
export WEBHOOK_SECRET=your-secret
```

2. Start the service:

```bash
make up
```

3. Service will be available at:

- http://localhost:8000

4. Stop the service:

```bash
make down
```

### Local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=sqlite:////data/app.db
export WEBHOOK_SECRET=your-secret
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Example curl commands

### Liveness

```bash
curl -i http://localhost:8000/health/live
```

### Readiness

```bash
curl -i http://localhost:8000/health/ready
```

### Create a webhook message

Body example:

```json
{
  "message_id": "msg-1",
  "from": "+14155550100",
  "to": "+14155550101",
  "ts": "2025-01-15T10:00:00Z",
  "text": "hello"
}
```

Compute signature (hex HMAC-SHA256 of raw body bytes):

```bash
BODY='{"message_id":"msg-1","from":"+14155550100","to":"+14155550101","ts":"2025-01-15T10:00:00Z","text":"hello"}'
SIG=$(WEBHOOK_SECRET="$WEBHOOK_SECRET" BODY="$BODY" python -c "import hmac,hashlib,os;print(hmac.new(os.environ['WEBHOOK_SECRET'].encode(), os.environ['BODY'].encode(), hashlib.sha256).hexdigest())")
```

Send:

```bash
curl -i -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Signature: $SIG" \
  -d "$BODY"
```

Expected response:

```json
{ "status": "ok" }
```

### List messages

```bash
curl -s "http://localhost:8000/messages?limit=50&offset=0" | jq .
```

Filters are combinable:

```bash
curl -s "http://localhost:8000/messages?from=%2B14155550100&since=2025-01-01T00:00:00Z&q=hello" | jq .
```

### Stats

```bash
curl -s http://localhost:8000/stats | jq .
```

### Prometheus metrics

```bash
curl -s http://localhost:8000/metrics
```

## Design decisions

### HMAC verification

- The service verifies `X-Signature` as `hex(HMAC_SHA256(secret=WEBHOOK_SECRET, message=RAW_REQUEST_BODY_BYTES))`.
- Uses `hmac.compare_digest` for constant-time comparison.
- Verification happens before JSON parsing and before any DB writes.

### Idempotency

- `message_id` is the SQLite `PRIMARY KEY`.
- Duplicate inserts are treated as success (ignored) and still return `{ "status": "ok" }`.

### Pagination logic

- `GET /messages` supports `limit` (default 50, min 1, max 100) and `offset` (default 0).
- `total` is computed separately and ignores pagination.
- Ordering is deterministic: `ORDER BY ts ASC, message_id ASC`.

### Stats computation

- `total_messages`: `COUNT(*)`
- `senders_count`: `COUNT(DISTINCT from_msisdn)`
- `messages_per_sender`: top 10 senders by count (desc), tie-break sender (asc)
- `first_message_ts`/`last_message_ts`: `MIN(ts)`/`MAX(ts)` (null when empty)

### Setup used (AI tools)

- Cascade (Windsurf) as an agentic pair programmer.

## Final self-test (matches evaluator)

- `GET /health/live` returns 200
- `GET /health/ready` returns 200 when:
  - `WEBHOOK_SECRET` set
  - DB reachable
  - schema applied
- Invalid signature returns 401
- Duplicate webhook returns 200
- `/messages` filters work and are combinable
- `/stats` returns correct counts
- Logs are JSON
- `/metrics` exists and returns Prometheus text
