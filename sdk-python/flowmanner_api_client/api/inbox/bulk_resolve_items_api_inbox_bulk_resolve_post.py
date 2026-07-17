from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.bulk_resolve_items_api_inbox_bulk_resolve_post_response_bulk_resolve_items_api_inbox_bulk_resolve_post import (
    BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost,
)
from ...models.bulk_resolve_request import BulkResolveRequest
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: BulkResolveRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/inbox/bulk-resolve",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError | None
):
    if response.status_code == 200:
        response_200 = BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost.from_dict(
            response.json()
        )

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
) -> Response[
    BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: BulkResolveRequest,
) -> Response[
    BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError
]:
    """Bulk Resolve Items

     Bulk resolve multiple inbox items.

    Approve or reject up to 100 items in one request. Items that cannot be
    resolved (not found, wrong status, forbidden) are skipped rather than
    failing the entire batch.

    Args:
        body (BulkResolveRequest): Request body for bulk inbox item resolution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError]
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
    body: BulkResolveRequest,
) -> (
    BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError | None
):
    """Bulk Resolve Items

     Bulk resolve multiple inbox items.

    Approve or reject up to 100 items in one request. Items that cannot be
    resolved (not found, wrong status, forbidden) are skipped rather than
    failing the entire batch.

    Args:
        body (BulkResolveRequest): Request body for bulk inbox item resolution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: BulkResolveRequest,
) -> Response[
    BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError
]:
    """Bulk Resolve Items

     Bulk resolve multiple inbox items.

    Approve or reject up to 100 items in one request. Items that cannot be
    resolved (not found, wrong status, forbidden) are skipped rather than
    failing the entire batch.

    Args:
        body (BulkResolveRequest): Request body for bulk inbox item resolution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: BulkResolveRequest,
) -> (
    BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError | None
):
    """Bulk Resolve Items

     Bulk resolve multiple inbox items.

    Approve or reject up to 100 items in one request. Items that cannot be
    resolved (not found, wrong status, forbidden) are skipped rather than
    failing the entire batch.

    Args:
        body (BulkResolveRequest): Request body for bulk inbox item resolution.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        BulkResolveItemsApiInboxBulkResolvePostResponseBulkResolveItemsApiInboxBulkResolvePost | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
