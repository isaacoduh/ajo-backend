"""Guarded demo reset command placeholder."""

import os
import sys

CONFIRMATION = "destroy-and-reseed"


def main() -> None:
    if os.getenv("DEMO_RESET_CONFIRM") != CONFIRMATION:
        print(
            "Refusing to reset demo data. Re-run with "
            f"DEMO_RESET_CONFIRM={CONFIRMATION} once Railway reset automation is configured.",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print("Demo reset automation is not wired yet; migrations and seed data are required first.")


if __name__ == "__main__":
    main()
