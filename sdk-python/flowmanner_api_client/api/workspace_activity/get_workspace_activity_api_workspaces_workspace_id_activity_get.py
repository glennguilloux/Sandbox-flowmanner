from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    workspace_id: str,
    *,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    event_type: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["limit"] = limit

    params["offset"] = offset

    json_event_type: None | str | Unset
    if isinstance(event_type, Unset):
        json_event_type = UNSET
    else:
        json_event_type = event_type
    params["event_type"] = json_event_type

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/workspaces/{workspace_id}/activity".format(
            workspace_id=quote(str(workspace_id), safe=""),
        ),
        "params": params,
    }

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
    workspace_id: str,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    event_type: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Get Workspace Activity

     Return recent workspace activity events.

    Filters analytics_events by workspace_id (stored in JSON properties)
    and event_type using database-level JSON operators.

    Args:
        workspace_id (str):
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        event_type (None | str | Unset): Filter by event type: role_changed, message_sent,
            member_online, mission_event

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
        event_type=event_type,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workspace_id: str,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    event_type: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Get Workspace Activity

     Return recent workspace activity events.

    Filters analytics_events by workspace_id (stored in JSON properties)
    and event_type using database-level JSON operators.

    Args:
        workspace_id (str):
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        event_type (None | str | Unset): Filter by event type: role_changed, message_sent,
            member_online, mission_event

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        workspace_id=workspace_id,
        client=client,
        limit=limit,
        offset=offset,
        event_type=event_type,
    ).parsed


async def asyncio_detailed(
    workspace_id: str,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    event_type: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Get Workspace Activity

     Return recent workspace activity events.

    Filters analytics_events by workspace_id (stored in JSON properties)
    and event_type using database-level JSON operators.

    Args:
        workspace_id (str):
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        event_type (None | str | Unset): Filter by event type: role_changed, message_sent,
            member_online, mission_event

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
        event_type=event_type,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workspace_id: str,
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    event_type: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Get Workspace Activity

     Return recent workspace activity events.

    Filters analytics_events by workspace_id (stored in JSON properties)
    and event_type using database-level JSON operators.

    Args:
        workspace_id (str):
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        event_type (None | str | Unset): Filter by event type: role_changed, message_sent,
            member_online, mission_event

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            workspace_id=workspace_id,
            client=client,
            limit=limit,
            offset=offset,
            event_type=event_type,
        )
    ).parsed
