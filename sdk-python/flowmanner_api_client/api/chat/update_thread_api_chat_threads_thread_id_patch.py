from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.chat_thread_response import ChatThreadResponse
from ...models.chat_thread_update import ChatThreadUpdate
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    thread_id: int,
    *,
    body: ChatThreadUpdate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/chat/threads/{thread_id}".format(
            thread_id=quote(str(thread_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ChatThreadResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ChatThreadResponse.from_dict(response.json())

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
) -> Response[ChatThreadResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    thread_id: int,
    *,
    client: AuthenticatedClient,
    body: ChatThreadUpdate,
) -> Response[ChatThreadResponse | HTTPValidationError]:
    """Update Thread

    Args:
        thread_id (int):
        body (ChatThreadUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatThreadResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        thread_id=thread_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    thread_id: int,
    *,
    client: AuthenticatedClient,
    body: ChatThreadUpdate,
) -> ChatThreadResponse | HTTPValidationError | None:
    """Update Thread

    Args:
        thread_id (int):
        body (ChatThreadUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatThreadResponse | HTTPValidationError
    """

    return sync_detailed(
        thread_id=thread_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    thread_id: int,
    *,
    client: AuthenticatedClient,
    body: ChatThreadUpdate,
) -> Response[ChatThreadResponse | HTTPValidationError]:
    """Update Thread

    Args:
        thread_id (int):
        body (ChatThreadUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatThreadResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        thread_id=thread_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    thread_id: int,
    *,
    client: AuthenticatedClient,
    body: ChatThreadUpdate,
) -> ChatThreadResponse | HTTPValidationError | None:
    """Update Thread

    Args:
        thread_id (int):
        body (ChatThreadUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatThreadResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            thread_id=thread_id,
            client=client,
            body=body,
        )
    ).parsed
