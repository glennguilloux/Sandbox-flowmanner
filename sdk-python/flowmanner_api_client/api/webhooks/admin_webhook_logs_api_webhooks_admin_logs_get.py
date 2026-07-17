from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    limit: int | Unset = 100,
    status_filter: None | str | Unset = UNSET,
    endpoint_id: int | None | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["limit"] = limit

    json_status_filter: None | str | Unset
    if isinstance(status_filter, Unset):
        json_status_filter = UNSET
    else:
        json_status_filter = status_filter
    params["status_filter"] = json_status_filter

    json_endpoint_id: int | None | Unset
    if isinstance(endpoint_id, Unset):
        json_endpoint_id = UNSET
    else:
        json_endpoint_id = endpoint_id
    params["endpoint_id"] = json_endpoint_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/webhooks/admin/logs",
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
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 100,
    status_filter: None | str | Unset = UNSET,
    endpoint_id: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Admin Webhook Logs

     Admin endpoint: last N webhook deliveries with aggregated stats.

    Returns the most recent deliveries across all (or filtered) endpoints,
    plus success rate, p95 latency, and per-status counts.

    Args:
        limit (int | Unset):  Default: 100.
        status_filter (None | str | Unset): Filter by status: pending, success, failed, retrying
        endpoint_id (int | None | Unset): Filter by endpoint ID

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        limit=limit,
        status_filter=status_filter,
        endpoint_id=endpoint_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 100,
    status_filter: None | str | Unset = UNSET,
    endpoint_id: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Admin Webhook Logs

     Admin endpoint: last N webhook deliveries with aggregated stats.

    Returns the most recent deliveries across all (or filtered) endpoints,
    plus success rate, p95 latency, and per-status counts.

    Args:
        limit (int | Unset):  Default: 100.
        status_filter (None | str | Unset): Filter by status: pending, success, failed, retrying
        endpoint_id (int | None | Unset): Filter by endpoint ID

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        limit=limit,
        status_filter=status_filter,
        endpoint_id=endpoint_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 100,
    status_filter: None | str | Unset = UNSET,
    endpoint_id: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Admin Webhook Logs

     Admin endpoint: last N webhook deliveries with aggregated stats.

    Returns the most recent deliveries across all (or filtered) endpoints,
    plus success rate, p95 latency, and per-status counts.

    Args:
        limit (int | Unset):  Default: 100.
        status_filter (None | str | Unset): Filter by status: pending, success, failed, retrying
        endpoint_id (int | None | Unset): Filter by endpoint ID

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        limit=limit,
        status_filter=status_filter,
        endpoint_id=endpoint_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 100,
    status_filter: None | str | Unset = UNSET,
    endpoint_id: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Admin Webhook Logs

     Admin endpoint: last N webhook deliveries with aggregated stats.

    Returns the most recent deliveries across all (or filtered) endpoints,
    plus success rate, p95 latency, and per-status counts.

    Args:
        limit (int | Unset):  Default: 100.
        status_filter (None | str | Unset): Filter by status: pending, success, failed, retrying
        endpoint_id (int | None | Unset): Filter by endpoint ID

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            limit=limit,
            status_filter=status_filter,
            endpoint_id=endpoint_id,
        )
    ).parsed
