from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.oidc_callback_response import OIDCCallbackResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    provider: str,
    *,
    code: str,
    redirect_uri: str,
    state: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["code"] = code

    params["redirect_uri"] = redirect_uri

    json_state: None | str | Unset
    if isinstance(state, Unset):
        json_state = UNSET
    else:
        json_state = state
    params["state"] = json_state

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/auth/oidc/{provider}/token".format(
            provider=quote(str(provider), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | OIDCCallbackResponse | None:
    if response.status_code == 200:
        response_200 = OIDCCallbackResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | OIDCCallbackResponse]:
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
    code: str,
    redirect_uri: str,
    state: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | OIDCCallbackResponse]:
    """Oidc Token Exchange

     Exchange authorization code for tokens (API endpoint).

    This is an alternative to the callback endpoint for SPAs that handle
    the redirect client-side and want to exchange the code via API.

    Request Body:
    - code: Authorization code from the OIDC provider
    - redirect_uri: The redirect URI used in the authorization request
    - state: State parameter for CSRF protection

    Args:
        provider (str):
        code (str):
        redirect_uri (str):
        state (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OIDCCallbackResponse]
    """

    kwargs = _get_kwargs(
        provider=provider,
        code=code,
        redirect_uri=redirect_uri,
        state=state,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    code: str,
    redirect_uri: str,
    state: None | str | Unset = UNSET,
) -> HTTPValidationError | OIDCCallbackResponse | None:
    """Oidc Token Exchange

     Exchange authorization code for tokens (API endpoint).

    This is an alternative to the callback endpoint for SPAs that handle
    the redirect client-side and want to exchange the code via API.

    Request Body:
    - code: Authorization code from the OIDC provider
    - redirect_uri: The redirect URI used in the authorization request
    - state: State parameter for CSRF protection

    Args:
        provider (str):
        code (str):
        redirect_uri (str):
        state (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OIDCCallbackResponse
    """

    return sync_detailed(
        provider=provider,
        client=client,
        code=code,
        redirect_uri=redirect_uri,
        state=state,
    ).parsed


async def asyncio_detailed(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    code: str,
    redirect_uri: str,
    state: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | OIDCCallbackResponse]:
    """Oidc Token Exchange

     Exchange authorization code for tokens (API endpoint).

    This is an alternative to the callback endpoint for SPAs that handle
    the redirect client-side and want to exchange the code via API.

    Request Body:
    - code: Authorization code from the OIDC provider
    - redirect_uri: The redirect URI used in the authorization request
    - state: State parameter for CSRF protection

    Args:
        provider (str):
        code (str):
        redirect_uri (str):
        state (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | OIDCCallbackResponse]
    """

    kwargs = _get_kwargs(
        provider=provider,
        code=code,
        redirect_uri=redirect_uri,
        state=state,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    code: str,
    redirect_uri: str,
    state: None | str | Unset = UNSET,
) -> HTTPValidationError | OIDCCallbackResponse | None:
    """Oidc Token Exchange

     Exchange authorization code for tokens (API endpoint).

    This is an alternative to the callback endpoint for SPAs that handle
    the redirect client-side and want to exchange the code via API.

    Request Body:
    - code: Authorization code from the OIDC provider
    - redirect_uri: The redirect URI used in the authorization request
    - state: State parameter for CSRF protection

    Args:
        provider (str):
        code (str):
        redirect_uri (str):
        state (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | OIDCCallbackResponse
    """

    return (
        await asyncio_detailed(
            provider=provider,
            client=client,
            code=code,
            redirect_uri=redirect_uri,
            state=state,
        )
    ).parsed
