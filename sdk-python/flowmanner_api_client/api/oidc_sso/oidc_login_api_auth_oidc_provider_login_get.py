from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.oidc_login_response import OIDCLoginResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    provider: str,
    *,
    redirect_uri: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_redirect_uri: None | str | Unset
    if isinstance(redirect_uri, Unset):
        json_redirect_uri = UNSET
    else:
        json_redirect_uri = redirect_uri
    params["redirect_uri"] = json_redirect_uri

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/auth/oidc/{provider}/login".format(
            provider=quote(str(provider), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | OIDCLoginResponse | None:
    if response.status_code == 200:
        response_200 = OIDCLoginResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | OIDCLoginResponse]:
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
    redirect_uri: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | OIDCLoginResponse]:
    """Oidc Login

     Initiate OIDC login flow with PKCE.

    Generates the authorization URL with PKCE challenge and returns it along with
    state/nonce. The frontend should redirect the user to the authorization_url.

    Query Parameters:
    - redirect_uri: Optional custom redirect URI for after authentication

    Args:
        provider (str):
        redirect_uri (None | str | Unset): Custom redirect URI after callback

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OIDCLoginResponse]
    """

    kwargs = _get_kwargs(
        provider=provider,
        redirect_uri=redirect_uri,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    redirect_uri: None | str | Unset = UNSET,
) -> HTTPValidationError | OIDCLoginResponse | None:
    """Oidc Login

     Initiate OIDC login flow with PKCE.

    Generates the authorization URL with PKCE challenge and returns it along with
    state/nonce. The frontend should redirect the user to the authorization_url.

    Query Parameters:
    - redirect_uri: Optional custom redirect URI for after authentication

    Args:
        provider (str):
        redirect_uri (None | str | Unset): Custom redirect URI after callback

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OIDCLoginResponse
    """

    return sync_detailed(
        provider=provider,
        client=client,
        redirect_uri=redirect_uri,
    ).parsed


async def asyncio_detailed(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    redirect_uri: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | OIDCLoginResponse]:
    """Oidc Login

     Initiate OIDC login flow with PKCE.

    Generates the authorization URL with PKCE challenge and returns it along with
    state/nonce. The frontend should redirect the user to the authorization_url.

    Query Parameters:
    - redirect_uri: Optional custom redirect URI for after authentication

    Args:
        provider (str):
        redirect_uri (None | str | Unset): Custom redirect URI after callback

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OIDCLoginResponse]
    """

    kwargs = _get_kwargs(
        provider=provider,
        redirect_uri=redirect_uri,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    redirect_uri: None | str | Unset = UNSET,
) -> HTTPValidationError | OIDCLoginResponse | None:
    """Oidc Login

     Initiate OIDC login flow with PKCE.

    Generates the authorization URL with PKCE challenge and returns it along with
    state/nonce. The frontend should redirect the user to the authorization_url.

    Query Parameters:
    - redirect_uri: Optional custom redirect URI for after authentication

    Args:
        provider (str):
        redirect_uri (None | str | Unset): Custom redirect URI after callback

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OIDCLoginResponse
    """

    return (
        await asyncio_detailed(
            provider=provider,
            client=client,
            redirect_uri=redirect_uri,
        )
    ).parsed
