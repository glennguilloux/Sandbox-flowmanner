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
    role_id: str,
    permission_key: str,
    *,
    tenant_id: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    params: dict[str, Any] = {}

    json_tenant_id: None | str | Unset
    if isinstance(tenant_id, Unset):
        json_tenant_id = UNSET
    else:
        json_tenant_id = tenant_id
    params["tenant_id"] = json_tenant_id


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/api/roles/{role_id}/permissions/{permission_key}".format(role_id=quote(str(role_id), safe=""),permission_key=quote(str(permission_key), safe=""),),
        "params": params,
    }


    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Any | HTTPValidationError | None:
    if response.status_code == 204:
        response_204 = cast(Any, None)
        return response_204

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
    role_id: str,
    permission_key: str,
    *,
    client: AuthenticatedClient,
    tenant_id: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Response[Any | HTTPValidationError]:
    """ Remove Permission

     Remove a permission key from a custom role.

    Args:
        role_id (str):
        permission_key (str):
        tenant_id (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        role_id=role_id,
permission_key=permission_key,
tenant_id=tenant_id,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    role_id: str,
    permission_key: str,
    *,
    client: AuthenticatedClient,
    tenant_id: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Any | HTTPValidationError | None:
    """ Remove Permission

     Remove a permission key from a custom role.

    Args:
        role_id (str):
        permission_key (str):
        tenant_id (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return sync_detailed(
        role_id=role_id,
permission_key=permission_key,
client=client,
tenant_id=tenant_id,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    role_id: str,
    permission_key: str,
    *,
    client: AuthenticatedClient,
    tenant_id: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Response[Any | HTTPValidationError]:
    """ Remove Permission

     Remove a permission key from a custom role.

    Args:
        role_id (str):
        permission_key (str):
        tenant_id (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
     """


    kwargs = _get_kwargs(
        role_id=role_id,
permission_key=permission_key,
tenant_id=tenant_id,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    role_id: str,
    permission_key: str,
    *,
    client: AuthenticatedClient,
    tenant_id: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Any | HTTPValidationError | None:
    """ Remove Permission

     Remove a permission key from a custom role.

    Args:
        role_id (str):
        permission_key (str):
        tenant_id (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
     """


    return (await asyncio_detailed(
        role_id=role_id,
permission_key=permission_key,
client=client,
tenant_id=tenant_id,
accept_version=accept_version,

    )).parsed
