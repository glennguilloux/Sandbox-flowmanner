from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.approve_item_api_inbox_item_id_approve_post_response_approve_item_api_inbox_item_id_approve_post import (
    ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.resolve_request import ResolveRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    item_id: str,
    *,
    body: None | ResolveRequest | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/inbox/{item_id}/approve".format(
            item_id=quote(str(item_id), safe=""),
        ),
    }

    if isinstance(body, ResolveRequest):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = body

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost.from_dict(
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
) -> Response[ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    item_id: str,
    *,
    client: AuthenticatedClient,
    body: None | ResolveRequest | Unset = UNSET,
) -> Response[ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError]:
    """Approve Item

     Approve an approval request. Resumes the paused mission.

    Args:
        item_id (str):
        body (None | ResolveRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    item_id: str,
    *,
    client: AuthenticatedClient,
    body: None | ResolveRequest | Unset = UNSET,
) -> ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError | None:
    """Approve Item

     Approve an approval request. Resumes the paused mission.

    Args:
        item_id (str):
        body (None | ResolveRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError
    """

    return sync_detailed(
        item_id=item_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    item_id: str,
    *,
    client: AuthenticatedClient,
    body: None | ResolveRequest | Unset = UNSET,
) -> Response[ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError]:
    """Approve Item

     Approve an approval request. Resumes the paused mission.

    Args:
        item_id (str):
        body (None | ResolveRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        item_id=item_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    item_id: str,
    *,
    client: AuthenticatedClient,
    body: None | ResolveRequest | Unset = UNSET,
) -> ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError | None:
    """Approve Item

     Approve an approval request. Resumes the paused mission.

    Args:
        item_id (str):
        body (None | ResolveRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApproveItemApiInboxItemIdApprovePostResponseApproveItemApiInboxItemIdApprovePost | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            item_id=item_id,
            client=client,
            body=body,
        )
    ).parsed
