from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    page: int | Unset = 1,
    limit: int | Unset = 20,
    source: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["page"] = page

    params["limit"] = limit

    json_source: None | str | Unset
    if isinstance(source, Unset):
        json_source = UNSET
    else:
        json_source = source
    params["source"] = json_source

    json_event_type: None | str | Unset
    if isinstance(event_type, Unset):
        json_event_type = UNSET
    else:
        json_event_type = event_type
    params["event_type"] = json_event_type

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    else:
        json_status = status
    params["status"] = json_status

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/external-events",
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
    page: int | Unset = 1,
    limit: int | Unset = 20,
    source: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List External Events

     List inbound integration events with filtering and pagination.

    Returns events scoped to the current user (if user_id is set on the event).
    Events without a user_id are visible to all authenticated users (system-wide events).

    Args:
        page (int | Unset):  Default: 1.
        limit (int | Unset):  Default: 20.
        source (None | str | Unset): Filter by integration source (e.g. 'github', 'stripe')
        event_type (None | str | Unset): Filter by event type (e.g. 'pull_request.opened')
        status (None | str | Unset): Filter by status: pending, processed, failed

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        page=page,
        limit=limit,
        source=source,
        event_type=event_type,
        status=status,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    limit: int | Unset = 20,
    source: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List External Events

     List inbound integration events with filtering and pagination.

    Returns events scoped to the current user (if user_id is set on the event).
    Events without a user_id are visible to all authenticated users (system-wide events).

    Args:
        page (int | Unset):  Default: 1.
        limit (int | Unset):  Default: 20.
        source (None | str | Unset): Filter by integration source (e.g. 'github', 'stripe')
        event_type (None | str | Unset): Filter by event type (e.g. 'pull_request.opened')
        status (None | str | Unset): Filter by status: pending, processed, failed

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        page=page,
        limit=limit,
        source=source,
        event_type=event_type,
        status=status,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    limit: int | Unset = 20,
    source: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List External Events

     List inbound integration events with filtering and pagination.

    Returns events scoped to the current user (if user_id is set on the event).
    Events without a user_id are visible to all authenticated users (system-wide events).

    Args:
        page (int | Unset):  Default: 1.
        limit (int | Unset):  Default: 20.
        source (None | str | Unset): Filter by integration source (e.g. 'github', 'stripe')
        event_type (None | str | Unset): Filter by event type (e.g. 'pull_request.opened')
        status (None | str | Unset): Filter by status: pending, processed, failed

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        page=page,
        limit=limit,
        source=source,
        event_type=event_type,
        status=status,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    limit: int | Unset = 20,
    source: None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List External Events

     List inbound integration events with filtering and pagination.

    Returns events scoped to the current user (if user_id is set on the event).
    Events without a user_id are visible to all authenticated users (system-wide events).

    Args:
        page (int | Unset):  Default: 1.
        limit (int | Unset):  Default: 20.
        source (None | str | Unset): Filter by integration source (e.g. 'github', 'stripe')
        event_type (None | str | Unset): Filter by event type (e.g. 'pull_request.opened')
        status (None | str | Unset): Filter by status: pending, processed, failed

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            page=page,
            limit=limit,
            source=source,
            event_type=event_type,
            status=status,
        )
    ).parsed
