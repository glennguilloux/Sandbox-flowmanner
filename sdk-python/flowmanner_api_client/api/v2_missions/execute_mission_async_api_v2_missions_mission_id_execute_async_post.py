from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.mission_execute_request import MissionExecuteRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    mission_id: UUID,
    *,
    body: MissionExecuteRequest | None | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/missions/{mission_id}/execute-async".format(
            mission_id=quote(str(mission_id), safe=""),
        ),
    }

    if isinstance(body, MissionExecuteRequest):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

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
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MissionExecuteRequest | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Execute Mission Async

    Args:
        mission_id (UUID):
        body (MissionExecuteRequest | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MissionExecuteRequest | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Execute Mission Async

    Args:
        mission_id (UUID):
        body (MissionExecuteRequest | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        mission_id=mission_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MissionExecuteRequest | None | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Execute Mission Async

    Args:
        mission_id (UUID):
        body (MissionExecuteRequest | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        mission_id=mission_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    mission_id: UUID,
    *,
    client: AuthenticatedClient,
    body: MissionExecuteRequest | None | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Execute Mission Async

    Args:
        mission_id (UUID):
        body (MissionExecuteRequest | None | Unset):

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
            body=body,
        )
    ).parsed
