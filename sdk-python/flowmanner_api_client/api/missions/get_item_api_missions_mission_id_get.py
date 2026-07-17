from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.mission_response import MissionResponse
from ...types import Response


def _get_kwargs(
    mission_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/missions/{mission_id}/".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MissionResponse | None:
    if response.status_code == 200:
        response_200 = MissionResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | MissionResponse]:
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
) -> Response[HTTPValidationError | MissionResponse]:
    """Get Item

    Args:
        mission_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MissionResponse]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | MissionResponse | None:
    """Get Item

    Args:
        mission_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MissionResponse
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | MissionResponse]:
    """Get Item

    Args:
        mission_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MissionResponse]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | MissionResponse | None:
    """Get Item

    Args:
        mission_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MissionResponse
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
        )
    ).parsed
