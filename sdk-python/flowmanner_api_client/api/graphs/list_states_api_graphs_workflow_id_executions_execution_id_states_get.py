from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.graph_state_response import GraphStateResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    workflow_id: UUID,
    execution_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/graphs/{workflow_id}/executions/{execution_id}/states".format(
            workflow_id=quote(str(workflow_id), safe=""),
            execution_id=quote(str(execution_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[GraphStateResponse] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = GraphStateResponse.from_dict(response_200_item_data)

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
) -> Response[HTTPValidationError | list[GraphStateResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    workflow_id: UUID,
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | list[GraphStateResponse]]:
    """List States

    Args:
        workflow_id (UUID):
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[GraphStateResponse]]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        execution_id=execution_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    workflow_id: UUID,
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | list[GraphStateResponse] | None:
    """List States

    Args:
        workflow_id (UUID):
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[GraphStateResponse]
    """

    return sync_detailed(
        workflow_id=workflow_id,
        execution_id=execution_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    workflow_id: UUID,
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | list[GraphStateResponse]]:
    """List States

    Args:
        workflow_id (UUID):
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[GraphStateResponse]]
    """

    kwargs = _get_kwargs(
        workflow_id=workflow_id,
        execution_id=execution_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    workflow_id: UUID,
    execution_id: UUID,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | list[GraphStateResponse] | None:
    """List States

    Args:
        workflow_id (UUID):
        execution_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[GraphStateResponse]
    """

    return (
        await asyncio_detailed(
            workflow_id=workflow_id,
            execution_id=execution_id,
            client=client,
        )
    ).parsed
