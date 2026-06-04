from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.oidc_logout_response import OIDCLogoutResponse
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    provider: str,
    *,
    id_token_hint: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    params: dict[str, Any] = {}

    json_id_token_hint: None | str | Unset
    if isinstance(id_token_hint, Unset):
        json_id_token_hint = UNSET
    else:
        json_id_token_hint = id_token_hint
    params["id_token_hint"] = json_id_token_hint


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/auth/oidc/{provider}/logout".format(provider=quote(str(provider), safe=""),),
        "params": params,
    }


    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | OIDCLogoutResponse | None:
    if response.status_code == 200:
        response_200 = OIDCLogoutResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | OIDCLogoutResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    id_token_hint: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | OIDCLogoutResponse]:
    """ Oidc Logout

     Logout from OIDC provider.

    Clears local tokens and returns the provider's end_session_url for redirect.

    Query Parameters:
    - id_token_hint: Optional ID token to include in logout request

    Args:
        provider (str):
        id_token_hint (None | str | Unset): ID token hint for logout
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OIDCLogoutResponse]
     """


    kwargs = _get_kwargs(
        provider=provider,
id_token_hint=id_token_hint,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    id_token_hint: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | OIDCLogoutResponse | None:
    """ Oidc Logout

     Logout from OIDC provider.

    Clears local tokens and returns the provider's end_session_url for redirect.

    Query Parameters:
    - id_token_hint: Optional ID token to include in logout request

    Args:
        provider (str):
        id_token_hint (None | str | Unset): ID token hint for logout
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OIDCLogoutResponse
     """


    return sync_detailed(
        provider=provider,
client=client,
id_token_hint=id_token_hint,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    id_token_hint: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | OIDCLogoutResponse]:
    """ Oidc Logout

     Logout from OIDC provider.

    Clears local tokens and returns the provider's end_session_url for redirect.

    Query Parameters:
    - id_token_hint: Optional ID token to include in logout request

    Args:
        provider (str):
        id_token_hint (None | str | Unset): ID token hint for logout
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OIDCLogoutResponse]
     """


    kwargs = _get_kwargs(
        provider=provider,
id_token_hint=id_token_hint,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    id_token_hint: None | str | Unset = UNSET,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | OIDCLogoutResponse | None:
    """ Oidc Logout

     Logout from OIDC provider.

    Clears local tokens and returns the provider's end_session_url for redirect.

    Query Parameters:
    - id_token_hint: Optional ID token to include in logout request

    Args:
        provider (str):
        id_token_hint (None | str | Unset): ID token hint for logout
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OIDCLogoutResponse
     """


    return (await asyncio_detailed(
        provider=provider,
client=client,
id_token_hint=id_token_hint,
accept_version=accept_version,

    )).parsed
