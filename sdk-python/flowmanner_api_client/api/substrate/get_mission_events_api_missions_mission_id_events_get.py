from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    mission_id: UUID,
    *,
    from_sequence: int | str | Unset = 0,
    to_sequence: int | None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    after_sequence: int | None | str | Unset = UNSET,
    limit: int | None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_from_sequence: int | str | Unset
    if isinstance(from_sequence, Unset):
        json_from_sequence = UNSET
    else:
        json_from_sequence = from_sequence
    params["from_sequence"] = json_from_sequence

    json_to_sequence: int | None | str | Unset
    if isinstance(to_sequence, Unset):
        json_to_sequence = UNSET
    else:
        json_to_sequence = to_sequence
    params["to_sequence"] = json_to_sequence

    json_event_type: None | str | Unset
    if isinstance(event_type, Unset):
        json_event_type = UNSET
    else:
        json_event_type = event_type
    params["event_type"] = json_event_type

    json_after_sequence: int | None | str | Unset
    if isinstance(after_sequence, Unset):
        json_after_sequence = UNSET
    else:
        json_after_sequence = after_sequence
    params["after_sequence"] = json_after_sequence

    json_limit: int | None | str | Unset
    if isinstance(limit, Unset):
        json_limit = UNSET
    else:
        json_limit = limit
    params["limit"] = json_limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/missions/{mission_id}/events".format(
            mission_id=quote(str(mission_id), safe=""),
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
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    from_sequence: int | str | Unset = 0,
    to_sequence: int | None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    after_sequence: int | None | str | Unset = UNSET,
    limit: int | None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    r"""Get Mission Events

     Fetch the substrate event log for a mission.

    Args:
        mission_id: Mission UUID.
        from_sequence: Inclusive lower bound (default: 0).
        to_sequence: Inclusive upper bound (default: no bound).
        event_type: Optional CSV filter by event type (e.g., \"task.completed,tool.call\").
        after_sequence: Inclusive cursor; returns events with sequence > after_sequence.
        limit: Max events to return (default: 100, max: 1000).

    Returns:
        dict with:
        - events: list of serialized events
        - total: total event count for this run
        - mission: { id, title, status }
        - run_id: the substrate run ID
        - next_after_sequence: cursor for the next page, when another page exists

    Args:
        mission_id (UUID):
        from_sequence (int | str | Unset):  Default: 0.
        to_sequence (int | None | str | Unset):
        event_type (None | str | Unset):
        after_sequence (int | None | str | Unset):
        limit (int | None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        event_type=event_type,
        after_sequence=after_sequence,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    from_sequence: int | str | Unset = 0,
    to_sequence: int | None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    after_sequence: int | None | str | Unset = UNSET,
    limit: int | None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    r"""Get Mission Events

     Fetch the substrate event log for a mission.

    Args:
        mission_id: Mission UUID.
        from_sequence: Inclusive lower bound (default: 0).
        to_sequence: Inclusive upper bound (default: no bound).
        event_type: Optional CSV filter by event type (e.g., \"task.completed,tool.call\").
        after_sequence: Inclusive cursor; returns events with sequence > after_sequence.
        limit: Max events to return (default: 100, max: 1000).

    Returns:
        dict with:
        - events: list of serialized events
        - total: total event count for this run
        - mission: { id, title, status }
        - run_id: the substrate run ID
        - next_after_sequence: cursor for the next page, when another page exists

    Args:
        mission_id (UUID):
        from_sequence (int | str | Unset):  Default: 0.
        to_sequence (int | None | str | Unset):
        event_type (None | str | Unset):
        after_sequence (int | None | str | Unset):
        limit (int | None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        event_type=event_type,
        after_sequence=after_sequence,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    from_sequence: int | str | Unset = 0,
    to_sequence: int | None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    after_sequence: int | None | str | Unset = UNSET,
    limit: int | None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    r"""Get Mission Events

     Fetch the substrate event log for a mission.

    Args:
        mission_id: Mission UUID.
        from_sequence: Inclusive lower bound (default: 0).
        to_sequence: Inclusive upper bound (default: no bound).
        event_type: Optional CSV filter by event type (e.g., \"task.completed,tool.call\").
        after_sequence: Inclusive cursor; returns events with sequence > after_sequence.
        limit: Max events to return (default: 100, max: 1000).

    Returns:
        dict with:
        - events: list of serialized events
        - total: total event count for this run
        - mission: { id, title, status }
        - run_id: the substrate run ID
        - next_after_sequence: cursor for the next page, when another page exists

    Args:
        mission_id (UUID):
        from_sequence (int | str | Unset):  Default: 0.
        to_sequence (int | None | str | Unset):
        event_type (None | str | Unset):
        after_sequence (int | None | str | Unset):
        limit (int | None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        from_sequence=from_sequence,
        to_sequence=to_sequence,
        event_type=event_type,
        after_sequence=after_sequence,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    from_sequence: int | str | Unset = 0,
    to_sequence: int | None | str | Unset = UNSET,
    event_type: None | str | Unset = UNSET,
    after_sequence: int | None | str | Unset = UNSET,
    limit: int | None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    r"""Get Mission Events

     Fetch the substrate event log for a mission.

    Args:
        mission_id: Mission UUID.
        from_sequence: Inclusive lower bound (default: 0).
        to_sequence: Inclusive upper bound (default: no bound).
        event_type: Optional CSV filter by event type (e.g., \"task.completed,tool.call\").
        after_sequence: Inclusive cursor; returns events with sequence > after_sequence.
        limit: Max events to return (default: 100, max: 1000).

    Returns:
        dict with:
        - events: list of serialized events
        - total: total event count for this run
        - mission: { id, title, status }
        - run_id: the substrate run ID
        - next_after_sequence: cursor for the next page, when another page exists

    Args:
        mission_id (UUID):
        from_sequence (int | str | Unset):  Default: 0.
        to_sequence (int | None | str | Unset):
        event_type (None | str | Unset):
        after_sequence (int | None | str | Unset):
        limit (int | None | str | Unset):

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
            from_sequence=from_sequence,
            to_sequence=to_sequence,
            event_type=event_type,
            after_sequence=after_sequence,
            limit=limit,
        )
    ).parsed
