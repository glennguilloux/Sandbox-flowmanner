from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.chat_thread_response import ChatThreadResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    thread_id: int,
    *,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/chat/threads/{thread_id}".format(thread_id=quote(str(thread_id), safe=""),),
    }


    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ChatThreadResponse | HTTPValidationError | None:
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


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ChatThreadResponse | HTTPValidationError]:
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
    accept_version: str | Unset = 'v1',

) -> Response[ChatThreadResponse | HTTPValidationError]:
    """ Get Thread

    Args:
        thread_id (int):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatThreadResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        thread_id=thread_id,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    thread_id: int,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = 'v1',

) -> ChatThreadResponse | HTTPValidationError | None:
    """ Get Thread

    Args:
        thread_id (int):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatThreadResponse | HTTPValidationError
     """


    return sync_detailed(
        thread_id=thread_id,
client=client,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    thread_id: int,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = 'v1',

) -> Response[ChatThreadResponse | HTTPValidationError]:
    """ Get Thread

    Args:
        thread_id (int):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatThreadResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        thread_id=thread_id,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    thread_id: int,
    *,
    client: AuthenticatedClient,
    accept_version: str | Unset = 'v1',

) -> ChatThreadResponse | HTTPValidationError | None:
    """ Get Thread

    Args:
        thread_id (int):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatThreadResponse | HTTPValidationError
     """


    return (await asyncio_detailed(
        thread_id=thread_id,
client=client,
accept_version=accept_version,

    )).parsed
