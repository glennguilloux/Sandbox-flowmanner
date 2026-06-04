from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.chat_folder_response import ChatFolderResponse
from ...models.chat_folder_update import ChatFolderUpdate
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    folder_id: int,
    *,
    body: ChatFolderUpdate,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/chat/folders/{folder_id}".format(folder_id=quote(str(folder_id), safe=""),),
    }

    _kwargs["json"] = body.to_dict()


    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ChatFolderResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = ChatFolderResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[ChatFolderResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    folder_id: int,
    *,
    client: AuthenticatedClient,
    body: ChatFolderUpdate,
    accept_version: str | Unset = 'v1',

) -> Response[ChatFolderResponse | HTTPValidationError]:
    """ Rename Folder

    Args:
        folder_id (int):
        accept_version (str | Unset):  Default: 'v1'.
        body (ChatFolderUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatFolderResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        folder_id=folder_id,
body=body,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    folder_id: int,
    *,
    client: AuthenticatedClient,
    body: ChatFolderUpdate,
    accept_version: str | Unset = 'v1',

) -> ChatFolderResponse | HTTPValidationError | None:
    """ Rename Folder

    Args:
        folder_id (int):
        accept_version (str | Unset):  Default: 'v1'.
        body (ChatFolderUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatFolderResponse | HTTPValidationError
     """


    return sync_detailed(
        folder_id=folder_id,
client=client,
body=body,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    folder_id: int,
    *,
    client: AuthenticatedClient,
    body: ChatFolderUpdate,
    accept_version: str | Unset = 'v1',

) -> Response[ChatFolderResponse | HTTPValidationError]:
    """ Rename Folder

    Args:
        folder_id (int):
        accept_version (str | Unset):  Default: 'v1'.
        body (ChatFolderUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ChatFolderResponse | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        folder_id=folder_id,
body=body,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    folder_id: int,
    *,
    client: AuthenticatedClient,
    body: ChatFolderUpdate,
    accept_version: str | Unset = 'v1',

) -> ChatFolderResponse | HTTPValidationError | None:
    """ Rename Folder

    Args:
        folder_id (int):
        accept_version (str | Unset):  Default: 'v1'.
        body (ChatFolderUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ChatFolderResponse | HTTPValidationError
     """


    return (await asyncio_detailed(
        folder_id=folder_id,
client=client,
body=body,
accept_version=accept_version,

    )).parsed
