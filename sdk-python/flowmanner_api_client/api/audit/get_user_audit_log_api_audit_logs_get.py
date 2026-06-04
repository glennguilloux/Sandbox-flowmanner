from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    action: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    params: dict[str, Any] = {}

    params["limit"] = limit

    params["offset"] = offset

    json_action: None | str | Unset
    if isinstance(action, Unset):
        json_action = UNSET
    else:
        json_action = action
    params["action"] = json_action


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/audit/logs/",
        "params": params,
    }


    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[Any | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    action: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Response[Any | HTTPValidationError]:
    """ Get User Audit Log

     Get audit log entries for the current user.

    Args:
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        action (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        limit=limit,
offset=offset,
action=action,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    action: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Any | HTTPValidationError | None:
    """ Get User Audit Log

     Get audit log entries for the current user.

    Args:
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        action (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return sync_detailed(
        client=client,
limit=limit,
offset=offset,
action=action,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    action: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Response[Any | HTTPValidationError]:
    """ Get User Audit Log

     Get audit log entries for the current user.

    Args:
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        action (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        limit=limit,
offset=offset,
action=action,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    limit: int | Unset = 50,
    offset: int | Unset = 0,
    action: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Any | HTTPValidationError | None:
    """ Get User Audit Log

     Get audit log entries for the current user.

    Args:
        limit (int | Unset):  Default: 50.
        offset (int | Unset):  Default: 0.
        action (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return (await asyncio_detailed(
        client=client,
limit=limit,
offset=offset,
action=action,
accept_version=accept_version,

    )).parsed
