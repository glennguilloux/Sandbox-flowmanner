from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.mission_execute_request import MissionExecuteRequest
from ...models.mission_execution_status import MissionExecutionStatus
from ...types import UNSET, Response, Unset


def _get_kwargs(
    mission_id: UUID,
    *,
    body: MissionExecuteRequest | None | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/missions/{mission_id}/execute".format(
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
) -> HTTPValidationError | MissionExecutionStatus | None:
    if response.status_code == 200:
        response_200 = MissionExecutionStatus.from_dict(response.json())

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
) -> Response[HTTPValidationError | MissionExecutionStatus]:
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
) -> Response[HTTPValidationError | MissionExecutionStatus]:
    """Execute Mission

    Args:
        mission_id (UUID):
        body (MissionExecuteRequest | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MissionExecutionStatus]
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
) -> HTTPValidationError | MissionExecutionStatus | None:
    """Execute Mission

    Args:
        mission_id (UUID):
        body (MissionExecuteRequest | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MissionExecutionStatus
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
) -> Response[HTTPValidationError | MissionExecutionStatus]:
    """Execute Mission

    Args:
        mission_id (UUID):
        body (MissionExecuteRequest | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MissionExecutionStatus]
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
) -> HTTPValidationError | MissionExecutionStatus | None:
    """Execute Mission

    Args:
        mission_id (UUID):
        body (MissionExecuteRequest | None | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MissionExecutionStatus
    """

    return (
        await asyncio_detailed(
            mission_id=mission_id,
            client=client,
            body=body,
        )
    ).parsed
