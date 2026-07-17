from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.depth_event_response import DepthEventResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    mission_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/missions/{mission_id}/depth-events".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[DepthEventResponse] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = DepthEventResponse.from_dict(response_200_item_data)

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
) -> Response[HTTPValidationError | list[DepthEventResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    mission_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | list[DepthEventResponse]]:
    """Get Depth Events

     List all depth_decided substrate events for a mission.

    Used for replay audit — shows why shallow vs deep was chosen
    for each step in a mission.

    Args:
        mission_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[DepthEventResponse]]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | list[DepthEventResponse] | None:
    """Get Depth Events

     List all depth_decided substrate events for a mission.

    Used for replay audit — shows why shallow vs deep was chosen
    for each step in a mission.

    Args:
        mission_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[DepthEventResponse]
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    mission_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[HTTPValidationError | list[DepthEventResponse]]:
    """Get Depth Events

     List all depth_decided substrate events for a mission.

    Used for replay audit — shows why shallow vs deep was chosen
    for each step in a mission.

    Args:
        mission_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[DepthEventResponse]]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: str,
    *,
    client: AuthenticatedClient | Client,
) -> HTTPValidationError | list[DepthEventResponse] | None:
    """Get Depth Events

     List all depth_decided substrate events for a mission.

    Used for replay audit — shows why shallow vs deep was chosen
    for each step in a mission.

    Args:
        mission_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[DepthEventResponse]
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
        )
    ).parsed
