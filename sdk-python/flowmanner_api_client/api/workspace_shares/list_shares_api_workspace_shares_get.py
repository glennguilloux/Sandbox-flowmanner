from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.share_response_3 import ShareResponse3
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    direction: str | Unset = "outgoing",
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["direction"] = direction

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/workspace-shares/",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[ShareResponse3] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = ShareResponse3.from_dict(response_200_item_data)

            response_200.append(response_200_item)

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
) -> Response[HTTPValidationError | list[ShareResponse3]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    direction: str | Unset = "outgoing",
) -> Response[HTTPValidationError | list[ShareResponse3]]:
    """List Shares

     List cross-workspace shares for the current workspace.

    direction='outgoing': shares granted BY this workspace (default).
    direction='incoming': shares granted TO this workspace.

    Args:
        direction (str | Unset):  Default: 'outgoing'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ShareResponse3]]
    """

    kwargs = _get_kwargs(
        direction=direction,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    direction: str | Unset = "outgoing",
) -> HTTPValidationError | list[ShareResponse3] | None:
    """List Shares

     List cross-workspace shares for the current workspace.

    direction='outgoing': shares granted BY this workspace (default).
    direction='incoming': shares granted TO this workspace.

    Args:
        direction (str | Unset):  Default: 'outgoing'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ShareResponse3]
    """

    return sync_detailed(
        client=client,
        direction=direction,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    direction: str | Unset = "outgoing",
) -> Response[HTTPValidationError | list[ShareResponse3]]:
    """List Shares

     List cross-workspace shares for the current workspace.

    direction='outgoing': shares granted BY this workspace (default).
    direction='incoming': shares granted TO this workspace.

    Args:
        direction (str | Unset):  Default: 'outgoing'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ShareResponse3]]
    """

    kwargs = _get_kwargs(
        direction=direction,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    direction: str | Unset = "outgoing",
) -> HTTPValidationError | list[ShareResponse3] | None:
    """List Shares

     List cross-workspace shares for the current workspace.

    direction='outgoing': shares granted BY this workspace (default).
    direction='incoming': shares granted TO this workspace.

    Args:
        direction (str | Unset):  Default: 'outgoing'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ShareResponse3]
    """

    return (
        await asyncio_detailed(
            client=client,
            direction=direction,
        )
    ).parsed
