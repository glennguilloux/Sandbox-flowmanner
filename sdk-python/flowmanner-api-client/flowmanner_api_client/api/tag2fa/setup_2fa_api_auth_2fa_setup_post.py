from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.totp_setup_response import TOTPSetupResponse
from ...types import Response


def _get_kwargs() -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/auth/2fa/setup",
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> TOTPSetupResponse | None:
    if response.status_code == 200:
        response_200 = TOTPSetupResponse.from_dict(response.json())

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[TOTPSetupResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[TOTPSetupResponse]:
    """Setup 2Fa

     Generate TOTP secret and QR code for 2FA setup.

    The user must verify the setup with a code from their authenticator app.
    Until verified, 2FA is not enabled.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TOTPSetupResponse]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> TOTPSetupResponse | None:
    """Setup 2Fa

     Generate TOTP secret and QR code for 2FA setup.

    The user must verify the setup with a code from their authenticator app.
    Until verified, 2FA is not enabled.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TOTPSetupResponse
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[TOTPSetupResponse]:
    """Setup 2Fa

     Generate TOTP secret and QR code for 2FA setup.

    The user must verify the setup with a code from their authenticator app.
    Until verified, 2FA is not enabled.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[TOTPSetupResponse]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> TOTPSetupResponse | None:
    """Setup 2Fa

     Generate TOTP secret and QR code for 2FA setup.

    The user must verify the setup with a code from their authenticator app.
    Until verified, 2FA is not enabled.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        TOTPSetupResponse
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
