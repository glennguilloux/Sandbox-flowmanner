from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    webhook_id: str,
    *,
    limit: int | Unset = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v3/auth/webhooks/{webhook_id}/deliveries".format(
            webhook_id=quote(str(webhook_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    webhook_id: str,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
) -> Response[Any | HTTPValidationError]:
    """List Webhook Deliveries

     List recent deliveries for a webhook subscription.

    Returns delivery log entries with status, response code, and retry info.
    The webhook delivery log is stored in the ``auth_webhook_delivery_logs``
    table (created by the delivery helper).

    Returns:
        200: { data: [{ id, event_type, status, response_code, attempt, ... }], ... }
        404: Webhook not found

    Args:
        webhook_id (str):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        webhook_id=webhook_id,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    webhook_id: str,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
) -> Any | HTTPValidationError | None:
    """List Webhook Deliveries

     List recent deliveries for a webhook subscription.

    Returns delivery log entries with status, response code, and retry info.
    The webhook delivery log is stored in the ``auth_webhook_delivery_logs``
    table (created by the delivery helper).

    Returns:
        200: { data: [{ id, event_type, status, response_code, attempt, ... }], ... }
        404: Webhook not found

    Args:
        webhook_id (str):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        webhook_id=webhook_id,
        client=client,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    webhook_id: str,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
) -> Response[Any | HTTPValidationError]:
    """List Webhook Deliveries

     List recent deliveries for a webhook subscription.

    Returns delivery log entries with status, response code, and retry info.
    The webhook delivery log is stored in the ``auth_webhook_delivery_logs``
    table (created by the delivery helper).

    Returns:
        200: { data: [{ id, event_type, status, response_code, attempt, ... }], ... }
        404: Webhook not found

    Args:
        webhook_id (str):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        webhook_id=webhook_id,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    webhook_id: str,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
) -> Any | HTTPValidationError | None:
    """List Webhook Deliveries

     List recent deliveries for a webhook subscription.

    Returns delivery log entries with status, response code, and retry info.
    The webhook delivery log is stored in the ``auth_webhook_delivery_logs``
    table (created by the delivery helper).

    Returns:
        200: { data: [{ id, event_type, status, response_code, attempt, ... }], ... }
        404: Webhook not found

    Args:
        webhook_id (str):
        limit (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            webhook_id=webhook_id,
            client=client,
            limit=limit,
        )
    ).parsed
