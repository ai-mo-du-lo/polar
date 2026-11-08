"""FixBugs demo seed: data that reaches each reverted bug over HTTP.

Run inside the api container after the normal seed:

    uv run python -m scripts.fixbugs_demo_seed

Prints one JSON manifest: a local organization access token plus the ids
each bug request needs. The token only works against this local database.

    bug     request                                   needs
    10567   PATCH /v1/subscriptions/{seat_sub}        seat product, 100% discount
    8338    PATCH /v1/customers/{customer}            any customer
    5922    PATCH /v1/subscriptions/{metered_sub}     two products, same meter
"""

import asyncio
import json
import uuid
from decimal import Decimal

from sqlalchemy import select

from polar.enums import SubscriptionRecurringInterval
from polar.kit.crypto import generate_token_hash_pair
from polar.models import Organization
from polar.models.discount import DiscountDuration, DiscountType
from polar.models.organization_access_token import OrganizationAccessToken
from polar.kit.db.postgres import create_async_sessionmaker
from polar.postgres import create_async_engine
from scripts.seeds_load import TOKEN_SCOPES
from tests.fixtures.database import save_fixture_factory
from tests.fixtures.random_objects import (
    create_active_subscription,
    create_customer,
    create_discount,
    create_meter,
    create_product,
    create_subscription_with_seats,
)

DEMO_ORG_SLUG = "acme-corp"
TOKEN_COMMENT = "FixBugs demo seed"
MONTH = SubscriptionRecurringInterval.month


async def seed() -> dict[str, str]:
    engine = create_async_engine("script")
    sessionmaker = create_async_sessionmaker(engine)

    async with sessionmaker() as session:
        save = save_fixture_factory(session)
        org = (
            await session.execute(
                select(Organization).where(Organization.slug == DEMO_ORG_SLUG)
            )
        ).scalar_one()

        # Local-only token for the Locust scenarios.
        token, token_hash = generate_token_hash_pair(prefix="polar_oat_")
        session.add(
            OrganizationAccessToken(
                organization_id=org.id,
                token=token_hash,
                scope=TOKEN_SCOPES,
                comment=TOKEN_COMMENT,
            )
        )

        # No Stripe id: customer updates must not call Stripe.
        customer = await create_customer(
            save,
            organization=org,
            email=f"demo-{uuid.uuid4().hex[:8]}@example.com",
            name="Demo Customer",
            stripe_customer_id=None,
        )

        # 10567: one seat at $10 with a 100% forever discount.
        seat_product = await create_product(
            save,
            organization=org,
            name="Team seats",
            recurring_interval=MONTH,
            prices=[("seat", 1000, "usd")],
        )
        discount = await create_discount(
            save,
            type=DiscountType.percentage,
            basis_points=10_000,
            duration=DiscountDuration.forever,
            organization=org,
            name="Startup program 100%",
            products=[seat_product],
        )
        seat_sub = await create_subscription_with_seats(
            save,
            product=seat_product,
            customer=customer,
            seats=1,
            discount=discount,
        )

        # 5922: fixed + metered plan, upgrade target bills the same meter.
        meter = await create_meter(save, organization=org, id=uuid.uuid4(), name="API calls")
        basic = await create_product(
            save,
            organization=org,
            name="Basic + usage",
            recurring_interval=MONTH,
            prices=[(1000, "usd"), (meter, Decimal(50), None, "usd")],
        )
        pro = await create_product(
            save,
            organization=org,
            name="Pro + usage",
            recurring_interval=MONTH,
            prices=[(3000, "usd"), (meter, Decimal(50), None, "usd")],
        )
        metered_sub = await create_active_subscription(
            save, product=basic, customer=customer
        )

        await session.commit()

    await engine.dispose()
    return {
        "token": token,
        "customer_id": str(customer.id),
        "seat_subscription_id": str(seat_sub.id),
        "metered_subscription_id": str(metered_sub.id),
        "upgrade_product_id": str(pro.id),
    }


if __name__ == "__main__":
    print(json.dumps(asyncio.run(seed())))
