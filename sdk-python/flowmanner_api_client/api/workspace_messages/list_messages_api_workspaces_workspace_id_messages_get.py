from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    workspace_id: str,
    *,
    recipient_id: int,
    limit: int | Unset = 50,
    before_id: int | None | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["recipient_id"] = recipient_id

    params["limit"] = limit

    json_before_id: int | None | Unset
    if isinstance(before_id, Unset):
        json_before_id = UNSET
    else:
        json_before_id = before_id
    params["before_id"] = json_before_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/workspaces/{workspace_id}/messages".format(
            workspace_id=quote(str(workspace_id), safe=""),
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
    workspace_id: str,
    *,
    client: AuthenticatedClient,
    recipient_id: int,
    limit: int | Unset = 50,
    before_id: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List Messages

     Get DM history between the current user and recipient_id in this workspace.

    Ordered newest-first for efficient timeline display. Reverse on the client.
    Supports cursor-based pagination via before_id.

    Args:
        workspace_id (str):
        recipient_id (int): The other participant in the DM conversation
        limit (int | Unset):  Default: 50.
        before_id (int | None | Unset): Pagination: get messages older than this ID

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        recipient_id=recipient_id,
        limit=limit,
        before_id=before_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workspace_id: str,
    *,
    client: AuthenticatedClient,
    recipient_id: int,
    limit: int | Unset = 50,
    before_id: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List Messages

     Get DM history between the current user and recipient_id in this workspace.

    Ordered newest-first for efficient timeline display. Reverse on the client.
    Supports cursor-based pagination via before_id.

    Args:
        workspace_id (str):
        recipient_id (int): The other participant in the DM conversation
        limit (int | Unset):  Default: 50.
        before_id (int | None | Unset): Pagination: get messages older than this ID

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        workspace_id=workspace_id,
        client=client,
        recipient_id=recipient_id,
        limit=limit,
        before_id=before_id,
    ).parsed


async def asyncio_detailed(
    workspace_id: str,
    *,
    client: AuthenticatedClient,
    recipient_id: int,
    limit: int | Unset = 50,
    before_id: int | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List Messages

     Get DM history between the current user and recipient_id in this workspace.

    Ordered newest-first for efficient timeline display. Reverse on the client.
    Supports cursor-based pagination via before_id.

    Args:
        workspace_id (str):
        recipient_id (int): The other participant in the DM conversation
        limit (int | Unset):  Default: 50.
        before_id (int | None | Unset): Pagination: get messages older than this ID

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        recipient_id=recipient_id,
        limit=limit,
        before_id=before_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workspace_id: str,
    *,
    client: AuthenticatedClient,
    recipient_id: int,
    limit: int | Unset = 50,
    before_id: int | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List Messages

     Get DM history between the current user and recipient_id in this workspace.

    Ordered newest-first for efficient timeline display. Reverse on the client.
    Supports cursor-based pagination via before_id.

    Args:
        workspace_id (str):
        recipient_id (int): The other participant in the DM conversation
        limit (int | Unset):  Default: 50.
        before_id (int | None | Unset): Pagination: get messages older than this ID

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            workspace_id=workspace_id,
            client=client,
            recipient_id=recipient_id,
            limit=limit,
            before_id=before_id,
        )
    ).parsed
