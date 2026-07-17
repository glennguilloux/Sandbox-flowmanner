from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    interrupt_type: None | str | Unset = UNSET,
    mission_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_interrupt_type: None | str | Unset
    if isinstance(interrupt_type, Unset):
        json_interrupt_type = UNSET
    else:
        json_interrupt_type = interrupt_type
    params["interrupt_type"] = json_interrupt_type

    json_mission_id: None | str | Unset
    if isinstance(mission_id, Unset):
        json_mission_id = UNSET
    else:
        json_mission_id = mission_id
    params["mission_id"] = json_mission_id

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    else:
        json_status = status
    params["status"] = json_status

    params["limit"] = limit

    params["offset"] = offset

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/inbox/",
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
    interrupt_type: None | str | Unset = UNSET,
    mission_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Response[Any | HTTPValidationError]:
    """List Inbox

     List pending inbox items for the current user.

    Hardened (Q1-B chunk 3):
    - Validates interrupt_type against HumanInterruptType enum (422 on invalid)
    - Optional workspace_id filter for defense-in-depth

    Args:
        interrupt_type (None | str | Unset): Filter by type: approval, clarification, escalation
        mission_id (None | str | Unset): Filter by mission
        status (None | str | Unset): Filter by status
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        interrupt_type=interrupt_type,
        mission_id=mission_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    interrupt_type: None | str | Unset = UNSET,
    mission_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Any | HTTPValidationError | None:
    """List Inbox

     List pending inbox items for the current user.

    Hardened (Q1-B chunk 3):
    - Validates interrupt_type against HumanInterruptType enum (422 on invalid)
    - Optional workspace_id filter for defense-in-depth

    Args:
        interrupt_type (None | str | Unset): Filter by type: approval, clarification, escalation
        mission_id (None | str | Unset): Filter by mission
        status (None | str | Unset): Filter by status
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        interrupt_type=interrupt_type,
        mission_id=mission_id,
        status=status,
        limit=limit,
        offset=offset,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    interrupt_type: None | str | Unset = UNSET,
    mission_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Response[Any | HTTPValidationError]:
    """List Inbox

     List pending inbox items for the current user.

    Hardened (Q1-B chunk 3):
    - Validates interrupt_type against HumanInterruptType enum (422 on invalid)
    - Optional workspace_id filter for defense-in-depth

    Args:
        interrupt_type (None | str | Unset): Filter by type: approval, clarification, escalation
        mission_id (None | str | Unset): Filter by mission
        status (None | str | Unset): Filter by status
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        interrupt_type=interrupt_type,
        mission_id=mission_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    interrupt_type: None | str | Unset = UNSET,
    mission_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
) -> Any | HTTPValidationError | None:
    """List Inbox

     List pending inbox items for the current user.

    Hardened (Q1-B chunk 3):
    - Validates interrupt_type against HumanInterruptType enum (422 on invalid)
    - Optional workspace_id filter for defense-in-depth

    Args:
        interrupt_type (None | str | Unset): Filter by type: approval, clarification, escalation
        mission_id (None | str | Unset): Filter by mission
        status (None | str | Unset): Filter by status
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            interrupt_type=interrupt_type,
            mission_id=mission_id,
            status=status,
            limit=limit,
            offset=offset,
        )
    ).parsed
