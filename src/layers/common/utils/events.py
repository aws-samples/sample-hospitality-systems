"""
EventBridge publisher for AnyCompany Hotel platform.

Publishes domain events to the central event bus following the
{domain}.{entity}.{action} naming convention for detail_type
and anycompany.{domain} for source.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import boto3

_client = None


def _get_client():
    """
    Return a cached EventBridge client.
    Reused across invocations within the same Lambda execution context.
    """
    global _client
    if _client is None:
        _client = boto3.client("events")
    return _client


def publish_event(
    source: str,
    detail_type: str,
    detail: dict[str, Any],
    correlation_id: str | None = None,
) -> dict:
    """
    Publish a domain event to the AnyCompany Hotel EventBridge bus.

    Args:
        source: Event source following "anycompany.{domain}" convention
                (e.g., "anycompany.reservations", "anycompany.payments").
        detail_type: Event type following "{domain}.{entity}.{action}"
                     convention (e.g., "reservation.created",
                     "guest.checked_in", "folio.settled").
        detail: Event payload dict containing the domain-specific data.
        correlation_id: Optional correlation ID for distributed tracing.
                        If not provided, a new UUID is generated.

    Returns:
        The EventBridge PutEvents response dict.

    Raises:
        botocore.exceptions.ClientError: If the EventBridge call fails.
    """
    bus_name = os.environ["EVENT_BUS_NAME"]
    client = _get_client()

    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    detail["_metadata"] = {
        "correlationId": correlation_id,
        "publishedAt": datetime.now(UTC).isoformat(),
        "source": source,
        "detailType": detail_type,
    }

    response = client.put_events(
        Entries=[
            {
                "Source": source,
                "DetailType": detail_type,
                "Detail": json.dumps(detail, default=str),
                "EventBusName": bus_name,
            }
        ]
    )

    return response


def publish_events(
    events: list[dict[str, Any]],
    correlation_id: str | None = None,
) -> dict:
    """
    Publish multiple domain events to EventBridge in a single batch.

    Each event dict must contain:
        - source: str
        - detail_type: str
        - detail: dict

    Args:
        events: List of event dicts to publish.
        correlation_id: Optional shared correlation ID for all events.

    Returns:
        The EventBridge PutEvents response dict.
    """
    bus_name = os.environ["EVENT_BUS_NAME"]
    client = _get_client()

    if correlation_id is None:
        correlation_id = str(uuid.uuid4())

    now = datetime.now(UTC).isoformat()

    entries = []
    for evt in events:
        detail = evt["detail"].copy()
        detail["_metadata"] = {
            "correlationId": correlation_id,
            "publishedAt": now,
            "source": evt["source"],
            "detailType": evt["detail_type"],
        }
        entries.append(
            {
                "Source": evt["source"],
                "DetailType": evt["detail_type"],
                "Detail": json.dumps(detail, default=str),
                "EventBusName": bus_name,
            }
        )

    response = client.put_events(Entries=entries)
    return response
