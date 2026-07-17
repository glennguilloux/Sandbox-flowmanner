from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    agent_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    execution_id: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_agent_id: None | str | Unset
    if isinstance(agent_id, Unset):
        json_agent_id = UNSET
    else:
        json_agent_id = agent_id
    params["agent_id"] = json_agent_id

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    else:
        json_status = status
    params["status"] = json_status

    json_execution_id: None | str | Unset
    if isinstance(execution_id, Unset):
        json_execution_id = UNSET
    else:
        json_execution_id = execution_id
    params["execution_id"] = json_execution_id

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/swarm/protocol/handoffs",
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
    *,
    client: AuthenticatedClient | Client,
    agent_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    execution_id: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[Any | HTTPValidationError]:
    """List Handoffs

     List handoffs with optional filters.

    Args:
        agent_id (None | str | Unset):
        status (None | str | Unset):
        execution_id (None | str | Unset):
        limit (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        agent_id=agent_id,
        status=status,
        execution_id=execution_id,
        limit=limit,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    agent_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    execution_id: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Any | HTTPValidationError | None:
    """List Handoffs

     List handoffs with optional filters.

    Args:
        agent_id (None | str | Unset):
        status (None | str | Unset):
        execution_id (None | str | Unset):
        limit (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        agent_id=agent_id,
        status=status,
        execution_id=execution_id,
        limit=limit,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    agent_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    execution_id: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Response[Any | HTTPValidationError]:
    """List Handoffs

     List handoffs with optional filters.

    Args:
        agent_id (None | str | Unset):
        status (None | str | Unset):
        execution_id (None | str | Unset):
        limit (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        agent_id=agent_id,
        status=status,
        execution_id=execution_id,
        limit=limit,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    agent_id: None | str | Unset = UNSET,
    status: None | str | Unset = UNSET,
    execution_id: None | str | Unset = UNSET,
    limit: int | Unset = 20,
) -> Any | HTTPValidationError | None:
    """List Handoffs

     List handoffs with optional filters.

    Args:
        agent_id (None | str | Unset):
        status (None | str | Unset):
        execution_id (None | str | Unset):
        limit (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            agent_id=agent_id,
            status=status,
            execution_id=execution_id,
            limit=limit,
        )
    ).parsed
