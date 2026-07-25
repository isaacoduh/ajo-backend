import pytest
from app.modules.payments.fake_rail import FakeRail
from app.modules.payments.port import PaymentRailPort
from app.modules.payments.types import (
    Capability,
    CollectionRequest,
    MandateRequest,
    PayoutRequest,
    RailMember,
    SettlementState,
    TopupRequest,
)


@pytest.fixture(params=[FakeRail])
def rail(request: pytest.FixtureRequest) -> PaymentRailPort:
    rail_class = request.param
    return rail_class()


def test_capabilities_are_queryable(rail: PaymentRailPort) -> None:
    assert rail.supports(Capability.TOPUPS)
    assert rail.supports(Capability.WEBHOOKS)


@pytest.mark.asyncio
async def test_onboarding_lifecycle(rail: PaymentRailPort) -> None:
    result = await rail.onboard_member(RailMember(user_id="user-1", email="user@example.com"))

    assert result.provider.value == rail.provider
    assert result.provider_member_id


@pytest.mark.asyncio
async def test_topup_idempotency(rail: PaymentRailPort) -> None:
    request = TopupRequest(idempotency_key="topup-key", user_id="user-1", amount_minor=1_000)

    first = await rail.create_topup(request)
    second = await rail.create_topup(request)

    assert first == second
    assert first.state == SettlementState.INITIATED
    assert first.amount_minor == 1_000


@pytest.mark.asyncio
async def test_mandate_and_collection_lifecycle(rail: PaymentRailPort) -> None:
    mandate = await rail.create_mandate(MandateRequest(idempotency_key="mandate-key", user_id="user-1"))
    collection = await rail.collect(
        CollectionRequest(
            idempotency_key="collection-key",
            mandate_id=mandate.provider_object_id,
            amount_minor=2_500,
        )
    )

    assert collection.state == SettlementState.INITIATED
    assert collection.amount_minor == 2_500


@pytest.mark.asyncio
async def test_payout_lifecycle(rail: PaymentRailPort) -> None:
    payout = await rail.send_payout(
        PayoutRequest(idempotency_key="payout-key", user_id="user-1", amount_minor=3_000)
    )

    assert payout.state == SettlementState.INITIATED
    assert payout.amount_minor == 3_000


@pytest.mark.asyncio
async def test_settlement_and_late_failure(rail: PaymentRailPort) -> None:
    topup = await rail.create_topup(
        TopupRequest(idempotency_key="late-failure-key", user_id="user-1", amount_minor=1_000)
    )

    settled = rail.settle(topup.provider_object_id)  # type: ignore[attr-defined]
    late_failed = rail.fail_late(topup.provider_object_id)  # type: ignore[attr-defined]

    assert settled.state == SettlementState.SETTLED
    assert late_failed.state == SettlementState.FAILED_LATE
    assert (await rail.get_settlement_status(topup.provider_object_id)).state == SettlementState.FAILED_LATE


@pytest.mark.asyncio
async def test_webhook_round_trip(rail: PaymentRailPort) -> None:
    topup = await rail.create_topup(
        TopupRequest(idempotency_key="webhook-key", user_id="user-1", amount_minor=1_000)
    )
    body = rail.webhook_payload(topup.provider_object_id)  # type: ignore[attr-defined]

    verified = await rail.verify_webhook(headers={}, body=body)

    assert verified.provider.value == rail.provider
    assert verified.provider_object_id == topup.provider_object_id
    assert verified.provider_event_id

    status = await rail.get_settlement_status(verified.provider_object_id)
    assert status.provider_object_id == topup.provider_object_id

