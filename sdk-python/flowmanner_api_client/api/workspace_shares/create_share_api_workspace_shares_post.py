from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.share_create_request import ShareCreateRequest
from ...models.share_response_3 import ShareResponse3
from ...types import Response


def _get_kwargs(
    *,
    body: ShareCreateRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/workspace-shares/",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ShareResponse3 | None:
    if response.status_code == 201:
        response_201 = ShareResponse3.from_dict(response.json())

        return response_201

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | ShareResponse3]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ShareCreateRequest,
) -> Response[HTTPValidationError | ShareResponse3]:
    """Create Share

     Grant cross-workspace access to a specific entity.

    The caller must be a member of the source workspace (the workspace that
    owns the entity). The entity_type and entity_id are validated against the
    source workspace's ownership.

    Args:
        body (ShareCreateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ShareResponse3]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: ShareCreateRequest,
) -> HTTPValidationError | ShareResponse3 | None:
    """Create Share

     Grant cross-workspace access to a specific entity.

    The caller must be a member of the source workspace (the workspace that
    owns the entity). The entity_type and entity_id are validated against the
    source workspace's ownership.

    Args:
        body (ShareCreateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ShareResponse3
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ShareCreateRequest,
) -> Response[HTTPValidationError | ShareResponse3]:
    """Create Share

     Grant cross-workspace access to a specific entity.

    The caller must be a member of the source workspace (the workspace that
    owns the entity). The entity_type and entity_id are validated against the
    source workspace's ownership.

    Args:
        body (ShareCreateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ShareResponse3]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ShareCreateRequest,
) -> HTTPValidationError | ShareResponse3 | None:
    """Create Share

     Grant cross-workspace access to a specific entity.

    The caller must be a member of the source workspace (the workspace that
    owns the entity). The entity_type and entity_id are validated against the
    source workspace's ownership.

    Args:
        body (ShareCreateRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ShareResponse3
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
