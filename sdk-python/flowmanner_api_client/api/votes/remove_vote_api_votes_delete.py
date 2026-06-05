from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.vote_out import VoteOut
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    item_id: str,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    params: dict[str, Any] = {}

    params["item_id"] = item_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/votes",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | VoteOut | None:
    if response.status_code == 200:
        response_200 = VoteOut.from_dict(response.json())

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
) -> Response[HTTPValidationError | VoteOut]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    item_id: str,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | VoteOut]:
    """Remove Vote

     Remove a vote from a roadmap item.

    Args:
        item_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | VoteOut]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    item_id: str,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | VoteOut | None:
    """Remove Vote

     Remove a vote from a roadmap item.

    Args:
        item_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | VoteOut
    """

    return sync_detailed(
        client=client,
        item_id=item_id,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    item_id: str,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | VoteOut]:
    """Remove Vote

     Remove a vote from a roadmap item.

    Args:
        item_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | VoteOut]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    item_id: str,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | VoteOut | None:
    """Remove Vote

     Remove a vote from a roadmap item.

    Args:
        item_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | VoteOut
    """

    return (
        await asyncio_detailed(
            client=client,
            item_id=item_id,
            accept_version=accept_version,
        )
    ).parsed
