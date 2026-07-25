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

The default test target runs the fast harness and contract suite without starting
Docker containers.

Container-backed tests are opt-in:

```bash
make test-containers
```

The shared test harness provides Postgres and Redis testcontainers fixtures for
tests marked `containers`.

## Notes

The application must not be run with live payment credentials. Config rejects
live-looking payment keys at startup.
