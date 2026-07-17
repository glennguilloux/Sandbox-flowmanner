from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.list_by_mission_api_inbox_by_mission_mission_id_get_response_200_item import (
    ListByMissionApiInboxByMissionMissionIdGetResponse200Item,
)
from ...types import Response


def _get_kwargs(
    mission_id: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/inbox/by-mission/{mission_id}".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = ListByMissionApiInboxByMissionMissionIdGetResponse200Item.from_dict(
                response_200_item_data
            )

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
) -> Response[HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item]]:
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
) -> Response[HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item]]:
    """List By Mission

     Get all inbox items for a mission, scoped to the current user.

    Args:
        mission_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item]]
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
    client: AuthenticatedClient,
) -> HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item] | None:
    """List By Mission

     Get all inbox items for a mission, scoped to the current user.

    Args:
        mission_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item]
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    mission_id: str,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item]]:
    """List By Mission

     Get all inbox items for a mission, scoped to the current user.

    Args:
        mission_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item]]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: str,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item] | None:
    """List By Mission

     Get all inbox items for a mission, scoped to the current user.

    Args:
        mission_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ListByMissionApiInboxByMissionMissionIdGetResponse200Item]
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
        )
    ).parsed
