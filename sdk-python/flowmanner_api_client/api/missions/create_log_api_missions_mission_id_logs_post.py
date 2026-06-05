from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.mission_log_create import MissionLogCreate
from ...models.mission_log_response import MissionLogResponse
from ...types import Response, Unset


def _get_kwargs(
    mission_id: UUID,
    *,
    body: MissionLogCreate,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/missions/{mission_id}/logs".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MissionLogResponse | None:
    if response.status_code == 201:
        response_201 = MissionLogResponse.from_dict(response.json())

        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | MissionLogResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MissionLogCreate,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | MissionLogResponse]:
    """Create Log

    Args:
        mission_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (MissionLogCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MissionLogResponse]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        body=body,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MissionLogCreate,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | MissionLogResponse | None:
    """Create Log

    Args:
        mission_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (MissionLogCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MissionLogResponse
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
        body=body,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MissionLogCreate,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | MissionLogResponse]:
    """Create Log

    Args:
        mission_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (MissionLogCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MissionLogResponse]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        body=body,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MissionLogCreate,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | MissionLogResponse | None:
    """Create Log

    Args:
        mission_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (MissionLogCreate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MissionLogResponse
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
            body=body,
            accept_version=accept_version,
        )
    ).parsed
