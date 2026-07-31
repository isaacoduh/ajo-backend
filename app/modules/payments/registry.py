"""Payment rail registry and flow selection."""

from app.core.config import RailName, Settings, get_settings
from app.modules.payments.fake_rail import FakeRail
from app.modules.payments.port import PaymentRailPort
from app.modules.payments.stripe_rail import StripeRail
from app.modules.payments.truelayer_rail import TrueLayerRail
from app.modules.payments.types import PaymentFlow


class PaymentRailRegistry:
    def __init__(self, rails: dict[str, PaymentRailPort]) -> None:
        self.rails = rails

    def by_name(self, name: str) -> PaymentRailPort:
        return self.rails[name]

    def for_flow(self, flow: PaymentFlow, settings: Settings | None = None) -> PaymentRailPort:
        resolved_settings = settings if settings is not None else get_settings()
        rail_name = {
            PaymentFlow.TOPUP: resolved_settings.rail_topup,
            PaymentFlow.COLLECTION: resolved_settings.rail_collection,
            PaymentFlow.PAYOUT: resolved_settings.rail_payout,
        }[flow]
        return self.by_name(rail_name.value)


def default_registry() -> PaymentRailRegistry:
    return PaymentRailRegistry(
        {
            RailName.FAKE.value: FakeRail(),
            RailName.STRIPE.value: StripeRail(),
            RailName.TRUELAYER.value: TrueLayerRail(),
        }
    )
