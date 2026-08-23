#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.providers.notion import notion_account


spaces = {
    "user-1": {
        "notion_user": {"user-1": {"value": {"email": "user@example.com"}}},
        "space": {
            "space-1": {
                "spaceId": "space-1",
                "value": {
                    "id": "space-1",
                    "name": "Example",
                    "plan_type": "team",
                    "subscription_tier": "business",
                },
            }
        },
    }
}
space_id, email, tier, name = notion_account(spaces)
assert space_id == "space-1"
assert email == "user@example.com"
assert tier == "business"
assert name == "Example"
print("notion collector tests passed")
