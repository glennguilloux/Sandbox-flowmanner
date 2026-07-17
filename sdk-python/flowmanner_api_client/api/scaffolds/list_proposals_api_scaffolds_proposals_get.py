from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.list_proposals_api_scaffolds_proposals_get_response_200_item import (
    ListProposalsApiScaffoldsProposalsGetResponse200Item,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    status: str | Unset = "pending",
    agent_id: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["status"] = status

    json_agent_id: None | str | Unset
    if isinstance(agent_id, Unset):
        json_agent_id = UNSET
    else:
        json_agent_id = agent_id
    params["agent_id"] = json_agent_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/scaffolds/proposals",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = ListProposalsApiScaffoldsProposalsGetResponse200Item.from_dict(response_200_item_data)

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
) -> Response[HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    status: str | Unset = "pending",
    agent_id: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item]]:
    """List Proposals

     List scaffold proposals, optionally filtered by status and agent.

    Args:
        status (str | Unset):  Default: 'pending'.
        agent_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item]]
    """

    kwargs = _get_kwargs(
        status=status,
        agent_id=agent_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    status: str | Unset = "pending",
    agent_id: None | str | Unset = UNSET,
) -> HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item] | None:
    """List Proposals

     List scaffold proposals, optionally filtered by status and agent.

    Args:
        status (str | Unset):  Default: 'pending'.
        agent_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item]
    """

    return sync_detailed(
        client=client,
        status=status,
        agent_id=agent_id,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    status: str | Unset = "pending",
    agent_id: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item]]:
    """List Proposals

     List scaffold proposals, optionally filtered by status and agent.

    Args:
        status (str | Unset):  Default: 'pending'.
        agent_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item]]
    """

    kwargs = _get_kwargs(
        status=status,
        agent_id=agent_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    status: str | Unset = "pending",
    agent_id: None | str | Unset = UNSET,
) -> HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item] | None:
    """List Proposals

     List scaffold proposals, optionally filtered by status and agent.

    Args:
        status (str | Unset):  Default: 'pending'.
        agent_id (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ListProposalsApiScaffoldsProposalsGetResponse200Item]
    """

    return (
        await asyncio_detailed(
            client=client,
            status=status,
            agent_id=agent_id,
        )
    ).parsed
