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

At this chassis stage, reset automation intentionally stops after confirmation
because seed data and Railway project variables are not implemented yet.

Required final behavior when seed data lands:

- set `ENV=demo`
- run Alembic migrations
- truncate/recreate demo-owned data only
- seed deterministic demo users, circles, ledger accounts, and fake rail objects
- reject live-mode payment credentials through normal config validation

Reset must preserve the no-live-money guarantee and use demo/sandbox-only
configuration.
