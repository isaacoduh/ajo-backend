# Railway Deploy

The demo deploy target is Railway with managed Postgres, managed Redis, and two
Dockerfile-backed services:

- API service
- Worker service

## Release Phase

Migrations run in the release phase before the API and worker accept traffic.

## Healthcheck

Railway should healthcheck `/readyz`. The endpoint verifies database and Redis
connectivity with short timeouts.

## Environment

Set `ENV=demo`. Do not set live-mode provider credentials; the application
rejects them at startup.

Detailed Railway commands land when deployment automation is added.

