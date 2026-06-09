from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.update_agent_registry_api_agent_registry_agents_agent_id_put_payload import (
    UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload,
)
from ...types import UNSET, Unset
from typing import cast
from uuid import UUID


def _get_kwargs(
    agent_id: UUID,
    *,
    body: UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/agent-registry/agents/{agent_id}".format(
            agent_id=quote(str(agent_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

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
    agent_id: UUID,
    *,
    client: AuthenticatedClient,
    body: UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload,
    accept_version: str | Unset = "v1",
) -> Response[Any | HTTPValidationError]:
    """Update Agent Registry

     Update an agent (full update via PUT).

    Args:
        agent_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        agent_id=agent_id,
        body=body,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    agent_id: UUID,
    *,
    client: AuthenticatedClient,
    body: UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload,
    accept_version: str | Unset = "v1",
) -> Any | HTTPValidationError | None:
    """Update Agent Registry

     Update an agent (full update via PUT).

    Args:
        agent_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        agent_id=agent_id,
        client=client,
        body=body,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    agent_id: UUID,
    *,
    client: AuthenticatedClient,
    body: UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload,
    accept_version: str | Unset = "v1",
) -> Response[Any | HTTPValidationError]:
    """Update Agent Registry

     Update an agent (full update via PUT).

    Args:
        agent_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        agent_id=agent_id,
        body=body,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    agent_id: UUID,
    *,
    client: AuthenticatedClient,
    body: UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload,
    accept_version: str | Unset = "v1",
) -> Any | HTTPValidationError | None:
    """Update Agent Registry

     Update an agent (full update via PUT).

    Args:
        agent_id (UUID):
        accept_version (str | Unset):  Default: 'v1'.
        body (UpdateAgentRegistryApiAgentRegistryAgentsAgentIdPutPayload):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            agent_id=agent_id,
            client=client,
            body=body,
            accept_version=accept_version,
        )
    ).parsed
