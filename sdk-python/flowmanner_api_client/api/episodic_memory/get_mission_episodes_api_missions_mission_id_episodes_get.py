from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.mission_episodes_response import MissionEpisodesResponse
from ...types import UNSET, Response


def _get_kwargs(
    mission_id: str,
    *,
    workspace_id: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["workspace_id"] = workspace_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/missions/{mission_id}/episodes".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MissionEpisodesResponse | None:
    if response.status_code == 200:
        response_200 = MissionEpisodesResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | MissionEpisodesResponse]:
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
    workspace_id: str,
) -> Response[HTTPValidationError | MissionEpisodesResponse]:
    """Get Mission Episodes

     List episodes that influenced a specific mission.

    Returns all episode records associated with the given mission,
    scoped to the requesting user's workspace.

    Args:
        mission_id (str):
        workspace_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MissionEpisodesResponse]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        workspace_id=workspace_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    workspace_id: str,
) -> HTTPValidationError | MissionEpisodesResponse | None:
    """Get Mission Episodes

     List episodes that influenced a specific mission.

    Returns all episode records associated with the given mission,
    scoped to the requesting user's workspace.

    Args:
        mission_id (str):
        workspace_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MissionEpisodesResponse
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
        workspace_id=workspace_id,
    ).parsed


async def asyncio_detailed(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    workspace_id: str,
) -> Response[HTTPValidationError | MissionEpisodesResponse]:
    """Get Mission Episodes

     List episodes that influenced a specific mission.

    Returns all episode records associated with the given mission,
    scoped to the requesting user's workspace.

    Args:
        mission_id (str):
        workspace_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MissionEpisodesResponse]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        workspace_id=workspace_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: str,
    *,
    client: AuthenticatedClient,
    workspace_id: str,
) -> HTTPValidationError | MissionEpisodesResponse | None:
    """Get Mission Episodes

     List episodes that influenced a specific mission.

    Returns all episode records associated with the given mission,
    scoped to the requesting user's workspace.

    Args:
        mission_id (str):
        workspace_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MissionEpisodesResponse
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
            workspace_id=workspace_id,
        )
    ).parsed
