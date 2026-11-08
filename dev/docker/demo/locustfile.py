"""FixBugs demo load: healthy background traffic plus one reverted bug at a time.

Started by `tools/demo-stack/cli.mjs load` in the FixBugs repo, e.g.
    locust ... BackgroundUser Bug8338User
Env: POLAR_DEMO_TOKEN (minted per run, never stored), DEMO_SEED (seed ids JSON).
Changing BackgroundUser changes TRAFFIC_PROFILE there; re-record the quiet window.
"""

import json
import os

from locust import HttpUser, constant_pacing, constant_throughput, task

SEED = json.loads(os.environ.get("DEMO_SEED", "{}"))
AUTH = {"Authorization": f"Bearer {os.environ.get('POLAR_DEMO_TOKEN', '')}"}

# A bug request every 45 s keeps its alert firing (2 min window).
BUG_PACING_SECONDS = 45


class BackgroundUser(HttpUser):
    """Seed reads only, about one request per second. Must never 5xx."""

    fixed_count = 1
    wait_time = constant_throughput(1)

    @task
    def customer(self) -> None:
        self.client.get(f"/v1/customers/{SEED['customer_id']}", headers=AUTH, name="/v1/customers/{id}")

    @task
    def seat_subscription(self) -> None:
        self.client.get(
            f"/v1/subscriptions/{SEED['seat_subscription_id']}", headers=AUTH, name="/v1/subscriptions/{id}"
        )

    @task
    def metered_subscription(self) -> None:
        self.client.get(
            f"/v1/subscriptions/{SEED['metered_subscription_id']}", headers=AUTH, name="/v1/subscriptions/{id}"
        )

    @task
    def product(self) -> None:
        self.client.get(f"/v1/products/{SEED['upgrade_product_id']}", headers=AUTH, name="/v1/products/{id}")


class BugUser(HttpUser):
    abstract = True
    fixed_count = 1
    wait_time = constant_pacing(BUG_PACING_SECONDS)


class Bug10567User(BugUser):
    """polarsource/polar#10567: seat update with a 100% discount."""

    @task
    def update_seats(self) -> None:
        self.client.patch(
            f"/v1/subscriptions/{SEED['seat_subscription_id']}",
            json={"seats": 2, "proration_behavior": "invoice"},
            headers=AUTH,
            name="#10567 seats",
        )


class Bug8338User(BugUser):
    """polarsource/polar#8338: customer billing_address update."""

    @task
    def update_billing_address(self) -> None:
        self.client.patch(
            f"/v1/customers/{SEED['customer_id']}",
            json={
                "billing_address": {
                    "country": "US",
                    "line1": "1 Main St",
                    "city": "Austin",
                    "state": "US-TX",
                    "postal_code": "78701",
                }
            },
            headers=AUTH,
            name="#8338 billing_address",
        )


class Bug5922User(BugUser):
    """polarsource/polar#5922: upgrade to a product with the same meter."""

    @task
    def upgrade(self) -> None:
        self.client.patch(
            f"/v1/subscriptions/{SEED['metered_subscription_id']}",
            json={"product_id": SEED["upgrade_product_id"], "proration_behavior": "prorate"},
            headers=AUTH,
            name="#5922 upgrade",
        )
