from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.restore_response import RestoreResponse
from ...types import Response, Unset


def _get_kwargs(
    mission_id: UUID,
    version_id: UUID,
    *,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/missions/advanced/missions/{mission_id}/versions/{version_id}/restore".format(
            mission_id=quote(str(mission_id), safe=""),
            version_id=quote(str(version_id), safe=""),
        ),
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | RestoreResponse | None:
    if response.status_code == 200:
        response_200 = RestoreResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | RestoreResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    mission_id: UUID,
    version_id: UUID,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | RestoreResponse]:
    """Restore Version

    Args:
        mission_id (UUID):
        version_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RestoreResponse]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        version_id=version_id,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: UUID,
    version_id: UUID,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | RestoreResponse | None:
    """Restore Version

    Args:
        mission_id (UUID):
        version_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RestoreResponse
    """

    return sync_detailed(
        mission_id=mission_id,
        version_id=version_id,
        client=client,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    mission_id: UUID,
    version_id: UUID,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | RestoreResponse]:
    """Restore Version

    Args:
        mission_id (UUID):
        version_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RestoreResponse]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        version_id=version_id,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: UUID,
    version_id: UUID,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | RestoreResponse | None:
    """Restore Version

    Args:
        mission_id (UUID):
        version_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RestoreResponse
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            version_id=version_id,
            client=client,
            accept_version=accept_version,
        )
    ).parsed
