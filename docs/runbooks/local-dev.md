# Local Development

Local development runs through Docker Compose.

## Start

```bash
make up
```

Services:

- API: `http://localhost:8000`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
- Mailpit UI: `http://localhost:8025`

## Test

```bash
make test
```

The test harness uses testcontainers for Postgres and Redis.

## Notes

The application must not be run with live payment credentials. Config rejects
live-looking payment keys at startup.

