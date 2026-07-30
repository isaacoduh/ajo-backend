# Demo Reset

The demo reset workflow must destroy and reseed the Railway demo environment in
one command once product seed data exists.

Current guarded command:

```bash
make demo-reset
```

The command refuses to run unless explicitly confirmed:

```bash
DEMO_RESET_CONFIRM=destroy-and-reseed make demo-reset
```

The command refuses to run in `ENV=production`. In `local`, `development`,
`staging`, and `test`, it clears product tables and runs the existing M1/M2 seed
flow again. It prints the seeded M1 login and the M2 circle ID for demo use.

Current behavior:

- requires `DEMO_RESET_CONFIRM=destroy-and-reseed`
- refuses `ENV=production`
- clears product tables in guarded demo-capable environments
- seeds deterministic M1 wallet data
- seeds an 8-member M2 circle that is locked and draw-revealed
- reject live-mode payment credentials through normal config validation

Run migrations before reset:

```bash
uv run alembic upgrade head
DEMO_RESET_CONFIRM=destroy-and-reseed make demo-reset
```

Railway staging reset still needs to be drilled against the actual staging
database before it is claimed pitch-ready.
