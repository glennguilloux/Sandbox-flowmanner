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
    *,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    params: dict[str, Any] = {}

    params["page"] = page

    params["per_page"] = per_page


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/chat/threads",
        "params": params,
    }


    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | list[ChatThreadResponse] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in (_response_200):
            response_200_item = ChatThreadResponse.from_dict(response_200_item_data)



            response_200.append(response_200_item)

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | list[ChatThreadResponse]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | list[ChatThreadResponse]]:
    """ List Threads Route

    Args:
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ChatThreadResponse]]
     """


    kwargs = _get_kwargs(
        page=page,
per_page=per_page,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | list[ChatThreadResponse] | None:
    """ List Threads Route

    Args:
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ChatThreadResponse]
     """


    return sync_detailed(
        client=client,
page=page,
per_page=per_page,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | list[ChatThreadResponse]]:
    """ List Threads Route

    Args:
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[ChatThreadResponse]]
     """


    kwargs = _get_kwargs(
        page=page,
per_page=per_page,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | list[ChatThreadResponse] | None:
    """ List Threads Route

    Args:
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[ChatThreadResponse]
     """


    return (await asyncio_detailed(
        client=client,
page=page,
per_page=per_page,
accept_version=accept_version,

    )).parsed
