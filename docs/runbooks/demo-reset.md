# Demo Reset

The demo reset runbook will destroy and reseed the demo environment in one
command once migrations and seed data exist.

Target command:

```bash
make demo-reset
```

Reset must preserve the no-live-money guarantee and use demo/sandbox-only
configuration.

