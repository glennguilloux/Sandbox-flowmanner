from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    provider: str,
    *,
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
    error_description: str | Unset = "",
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["code"] = code

    params["state"] = state

    params["error"] = error

    params["error_description"] = error_description

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v3/auth/oidc/{provider}/callback".format(
            provider=quote(str(provider), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 302:
        response_302 = response.json()
        return response_302

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Any | HTTPValidationError]:
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
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
    error_description: str | Unset = "",
) -> Response[Any | HTTPValidationError]:
    """Oidc Callback

     Handle OIDC callback after authentication.

    Exchanges the authorization code for tokens, finds or creates the user,
    creates a v3 session with httpOnly cookie, and redirects to the frontend.

    Returns:
        302: Redirect to frontend with session cookie set
        400: Missing code/state or authentication failure

    Args:
        provider (str):
        code (str | Unset):  Default: ''.
        state (str | Unset):  Default: ''.
        error (str | Unset):  Default: ''.
        error_description (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        provider=provider,
        code=code,
        state=state,
        error=error,
        error_description=error_description,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
    error_description: str | Unset = "",
) -> Any | HTTPValidationError | None:
    """Oidc Callback

     Handle OIDC callback after authentication.

    Exchanges the authorization code for tokens, finds or creates the user,
    creates a v3 session with httpOnly cookie, and redirects to the frontend.

    Returns:
        302: Redirect to frontend with session cookie set
        400: Missing code/state or authentication failure

    Args:
        provider (str):
        code (str | Unset):  Default: ''.
        state (str | Unset):  Default: ''.
        error (str | Unset):  Default: ''.
        error_description (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        provider=provider,
        client=client,
        code=code,
        state=state,
        error=error,
        error_description=error_description,
    ).parsed


async def asyncio_detailed(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
    error_description: str | Unset = "",
) -> Response[Any | HTTPValidationError]:
    """Oidc Callback

     Handle OIDC callback after authentication.

    Exchanges the authorization code for tokens, finds or creates the user,
    creates a v3 session with httpOnly cookie, and redirects to the frontend.

    Returns:
        302: Redirect to frontend with session cookie set
        400: Missing code/state or authentication failure

    Args:
        provider (str):
        code (str | Unset):  Default: ''.
        state (str | Unset):  Default: ''.
        error (str | Unset):  Default: ''.
        error_description (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        provider=provider,
        code=code,
        state=state,
        error=error,
        error_description=error_description,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    provider: str,
    *,
    client: AuthenticatedClient | Client,
    code: str | Unset = "",
    state: str | Unset = "",
    error: str | Unset = "",
    error_description: str | Unset = "",
) -> Any | HTTPValidationError | None:
    """Oidc Callback

     Handle OIDC callback after authentication.

    Exchanges the authorization code for tokens, finds or creates the user,
    creates a v3 session with httpOnly cookie, and redirects to the frontend.

    Returns:
        302: Redirect to frontend with session cookie set
        400: Missing code/state or authentication failure

    Args:
        provider (str):
        code (str | Unset):  Default: ''.
        state (str | Unset):  Default: ''.
        error (str | Unset):  Default: ''.
        error_description (str | Unset):  Default: ''.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            provider=provider,
            client=client,
            code=code,
            state=state,
            error=error,
            error_description=error_description,
        )
    ).parsed
