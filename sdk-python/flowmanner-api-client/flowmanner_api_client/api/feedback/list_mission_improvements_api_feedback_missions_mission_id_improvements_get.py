from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response, Unset


def _get_kwargs(
    mission_id: str,
    *,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/feedback/missions/{mission_id}/improvements".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
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
    mission_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[Any | HTTPValidationError]:
    """List Mission Improvements

     List improvement suggestions for a mission (from feedback synthesis).

    Args:
        mission_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Any | HTTPValidationError | None:
    """List Mission Improvements

     List improvement suggestions for a mission (from feedback synthesis).

    Args:
        mission_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[Any | HTTPValidationError]:
    """List Mission Improvements

     List improvement suggestions for a mission (from feedback synthesis).

    Args:
        mission_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Any | HTTPValidationError | None:
    """List Mission Improvements

     List improvement suggestions for a mission (from feedback synthesis).

    Args:
        mission_id (str):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
            accept_version=accept_version,
        )
    ).parsed
