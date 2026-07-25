# Railway Deploy

The demo deploy target is Railway with managed Postgres, managed Redis, and two
Dockerfile-backed services:

- API service
- Worker service

## Release Phase

Migrations run in the release phase before the API and worker accept traffic.

Recommended release command:

```bash
uv run alembic upgrade head
```

## Healthcheck

Railway should healthcheck `/readyz`. The endpoint verifies database and Redis
connectivity with short timeouts.

## Environment

Set `ENV=demo`. Do not set live-mode provider credentials; the application
rejects them at startup.

Required variables:

- `ENV=demo`
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_ACCESS_SECRET`
- `REFRESH_TOKEN_PEPPER`
- `RAIL_TOPUP=fake`
- `RAIL_COLLECTION=fake`
- `RAIL_PAYOUT=fake`
- `SMTP_HOST`
- `SMTP_PORT`

API service command:

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Worker service command:

```bash
uv run arq app.workers.main.WorkerSettings
```

Detailed Railway project provisioning commands land when deployment automation is
added.
