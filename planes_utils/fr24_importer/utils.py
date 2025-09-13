"""Common utilities for FlightRadar24 API integration."""

import os
import time
from typing import Optional

from fr24sdk.exceptions import ApiError, Fr24SdkError, RateLimitError

from . import SubscriptionPlan


def validate_api_key(fr24_api_key: Optional[str] = None) -> str:
    """Validate and return FR24 API key.
    
    Args:
        fr24_api_key: Optional FR24 API key. If None, uses FR24_API_TOKEN from environment.
        
    Returns:
        Valid API key string
        
    Raises:
        ValueError: If FR24_API_TOKEN not found in environment and fr24_api_key is None
    """
    if fr24_api_key is None:
        fr24_api_key = os.getenv("FR24_API_TOKEN")
        if not fr24_api_key:
            raise ValueError("FR24_API_TOKEN not found in environment variables")
    return fr24_api_key


def setup_rate_limiting(plan: Optional[SubscriptionPlan] = None) -> float:
    """Setup rate limiting based on subscription plan.
    
    Args:
        plan: Optional subscription plan for rate limiting. If None, no rate limiting is applied.
        
    Returns:
        Sleep time between requests in seconds (0 if no rate limiting)
    """
    if not plan:
        return 0
    
    request_rate_limit = plan.value.request_rate_limit
    sleep_time = 60 / request_rate_limit  # Convert requests/minute to seconds between requests
    print(f"Rate limit: {request_rate_limit} requests/minute, using {sleep_time:.2f}s delay between requests")
    return sleep_time


def apply_rate_limit(sleep_time: float, is_first_request: bool = False) -> None:
    """Apply rate limiting delay if needed.
    
    Args:
        sleep_time: Sleep time in seconds
        is_first_request: Whether this is the first request (no delay applied)
    """
    if sleep_time > 0 and not is_first_request:
        time.sleep(sleep_time)


def handle_fr24_exceptions(operation_name: str):
    """Context manager and decorator for handling FR24 API exceptions.
    
    Args:
        operation_name: Name of the operation being performed for error messages
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except RateLimitError:
                print(
                    "Rate limit exceeded: You have made too many requests to the FlightRadar24 API."
                )
                print("Please wait before making another request.")
                raise
            except ApiError as e:
                print(f"FR24 API Error during {operation_name}:")
                print(f"  Request URL: {e.request_url}")
                print(f"  Message: {e.message}")
                raise
            except Fr24SdkError as e:
                print(f"FR24 SDK Error during {operation_name}: {e}")
                raise
        return wrapper
    return decorator


def print_summary(title: str, **metrics: int | str) -> None:
    """Print a formatted summary with metrics.
    
    Args:
        title: Title of the summary
        **metrics: Key-value pairs of metrics to display
    """
    print("\n" + "=" * 60)
    print(title.upper())
    print("=" * 60)
    
    for key, value in metrics.items():
        # Convert snake_case to Title Case
        display_key = key.replace('_', ' ').title()
        print(f"{display_key}: {value}")
    
    print("=" * 60)