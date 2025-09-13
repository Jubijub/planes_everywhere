# Handle importing data from FlightRadar24 API
from dataclasses import dataclass
from enum import Enum
import os

from fr24sdk.client import Client
from fr24sdk.exceptions import RateLimitError


class UsagePeriod(Enum):
    TWENTY_FOUR_HOURS = "24h"
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"
    ONE_YEAR = "1y"


@dataclass
class PlanLimits:
    response_limit: int | None  # None means unlimited
    request_rate_limit: int  # requests per minute


class SubscriptionPlan(Enum):
    EXPLORER = PlanLimits(response_limit=20, request_rate_limit=10)
    ESSENTIAL = PlanLimits(response_limit=300, request_rate_limit=30)
    ADVANCED = PlanLimits(response_limit=None, request_rate_limit=90)


def initialize_package(plan: SubscriptionPlan) -> SubscriptionPlan:
    """Initialize the fr24_importer package with subscription plan limits.

    Args:
        plan: The FlightRadar24 subscription plan (EXPLORER, ESSENTIAL, or ADVANCED)
        
    Returns:
        The subscription plan that was initialized
    """
    limits = plan.value
    response_limit_str = (
        "unlimited" if limits.response_limit is None else str(limits.response_limit)
    )

    print(f"FR24 Importer initialized with {plan.name} plan:")
    print(f"  - Response limit: {response_limit_str} items per query")
    print(f"  - Request rate limit: {limits.request_rate_limit} requests per minute")
    
    return plan


def getUsage(period: UsagePeriod, fr24_api_key: str | None = None):
    """Get FlightRadar24 API usage statistics for a given period.

    Args:
        period: UsagePeriod enum specifying the time period
        fr24_api_key: Optional API key. If None, uses FR24_API_TOKEN from environment.

    Returns:
        None (prints formatted usage statistics)
    """
    if fr24_api_key is None:
        fr24_api_key = os.getenv("FR24_API_TOKEN")
        if not fr24_api_key:
            raise ValueError("FR24_API_TOKEN not found in environment variables")

    try:
        with Client(api_token=fr24_api_key) as client:
            usage_data = client.usage.get(period.value)

            if not usage_data.data:
                print(f"No usage data found for period: {period.value}")
                return

            total_credits = 0

            print(f"FlightRadar24 API Usage ({period.value}):")
            print("-" * 100)

            for usage_log in usage_data.data:
                print(
                    f"{usage_log.endpoint:<40} | Requests: {usage_log.request_count:>4} | Credits: {usage_log.credits:>6}"
                )
                total_credits += usage_log.credits

            print("-" * 100)
            print(f"{'Total Credits:':<40} | {total_credits:>17}")

    except RateLimitError:
        print(
            f"Rate limit exceeded: You have made too many requests to the FlightRadar24 API."
        )
        print(
            f"Please wait before making another request for usage data (period: {period.value})."
        )
