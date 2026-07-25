

from app.core.config import RailName, Settings
from app.modules.payments.fake_rail import FakeRail, valid_transition
from app.modules.payments.registry import PaymentRailRegistry
from app.modules.payments.types import PaymentFlow, SettlementState


def test_state_machine_allows_only_expected_transitions() -> None:
    assert valid_transition(SettlementState.INITIATED, SettlementState.PROCESSING)
    assert valid_transition(SettlementState.PROCESSING, SettlementState.SETTLED)
    assert valid_transition(SettlementState.PROCESSING, SettlementState.FAILED)
    assert valid_transition(SettlementState.SETTLED, SettlementState.FAILED_LATE)
    assert not valid_transition(SettlementState.SETTLED, SettlementState.FAILED)


def test_registry_selects_rail_per_flow() -> None:
    registry = PaymentRailRegistry({RailName.FAKE.value: FakeRail()})
    settings = Settings(
        ENV="test",
        DATABASE_URL="postgresql+asyncpg://ajo:ajo@localhost:5432/ajo",
        REDIS_URL="redis://localhost:6379/0",
        JWT_ACCESS_SECRET="local-only-access-secret-32-bytes",
        REFRESH_TOKEN_PEPPER="local-only-refresh-pepper-32-bytes",
        RAIL_TOPUP="fake",
        RAIL_COLLECTION="fake",
        RAIL_PAYOUT="fake",
    )

    assert registry.for_flow(PaymentFlow.TOPUP, settings).provider == "fake"
    assert registry.for_flow(PaymentFlow.COLLECTION, settings).provider == "fake"
    assert registry.for_flow(PaymentFlow.PAYOUT, settings).provider == "fake"

