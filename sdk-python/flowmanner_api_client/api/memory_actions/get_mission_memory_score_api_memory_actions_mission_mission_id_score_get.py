from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_mission_memory_score_api_memory_actions_mission_mission_id_score_get_response_get_mission_memory_score_api_memory_actions_mission_mission_id_score_get import (
    GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    mission_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/memory-actions/mission/{mission_id}/score".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet.from_dict(
            response.json()
        )

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
) -> Response[
    GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet
    | HTTPValidationError
]:
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
) -> Response[
    GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet
    | HTTPValidationError
]:
    """Get Mission Memory Score

     Return memory proficiency score for a mission's episode.

    Includes total/successful/failed counts, average latency,
    and per-action-type breakdown.

    Args:
        mission_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet | HTTPValidationError]
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
) -> (
    GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet
    | HTTPValidationError
    | None
):
    """Get Mission Memory Score

     Return memory proficiency score for a mission's episode.

    Includes total/successful/failed counts, average latency,
    and per-action-type breakdown.

    Args:
        mission_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet | HTTPValidationError
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[
    GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet
    | HTTPValidationError
]:
    """Get Mission Memory Score

     Return memory proficiency score for a mission's episode.

    Includes total/successful/failed counts, average latency,
    and per-action-type breakdown.

    Args:
        mission_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet | HTTPValidationError]
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
) -> (
    GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet
    | HTTPValidationError
    | None
):
    """Get Mission Memory Score

     Return memory proficiency score for a mission's episode.

    Includes total/successful/failed counts, average latency,
    and per-action-type breakdown.

    Args:
        mission_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGetResponseGetMissionMemoryScoreApiMemoryActionsMissionMissionIdScoreGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
        )
    ).parsed
