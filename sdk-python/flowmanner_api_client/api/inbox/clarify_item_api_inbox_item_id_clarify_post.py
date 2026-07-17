from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.clarify_item_api_inbox_item_id_clarify_post_response_clarify_item_api_inbox_item_id_clarify_post import (
    ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost,
)
from ...models.clarify_request import ClarifyRequest
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    item_id: str,
    *,
    body: ClarifyRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/inbox/{item_id}/clarify".format(
            item_id=quote(str(item_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost.from_dict(
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
) -> Response[ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError]:
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
    body: ClarifyRequest,
) -> Response[ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError]:
    """Clarify Item

     Respond to a clarification request. Resumes the paused mission with the response.

    Args:
        item_id (str):
        body (ClarifyRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError]
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
    body: ClarifyRequest,
) -> ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError | None:
    """Clarify Item

     Respond to a clarification request. Resumes the paused mission with the response.

    Args:
        item_id (str):
        body (ClarifyRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError
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
    body: ClarifyRequest,
) -> Response[ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError]:
    """Clarify Item

     Respond to a clarification request. Resumes the paused mission with the response.

    Args:
        item_id (str):
        body (ClarifyRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError]
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
    body: ClarifyRequest,
) -> ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError | None:
    """Clarify Item

     Respond to a clarification request. Resumes the paused mission with the response.

    Args:
        item_id (str):
        body (ClarifyRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ClarifyItemApiInboxItemIdClarifyPostResponseClarifyItemApiInboxItemIdClarifyPost | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            item_id=item_id,
            client=client,
            body=body,
        )
    ).parsed
