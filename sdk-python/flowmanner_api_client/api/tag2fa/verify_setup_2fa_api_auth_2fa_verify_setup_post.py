from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.totp_verify_setup_request import TOTPVerifySetupRequest
from ...models.totp_verify_setup_response import TOTPVerifySetupResponse
from typing import cast



def _get_kwargs(
    *,
    body: TOTPVerifySetupRequest,

) -> dict[str, Any]:
    headers: dict[str, Any] = {}


    

    

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/auth/2fa/verify-setup",
    }

    _kwargs["json"] = body.to_dict()


    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | TOTPVerifySetupResponse | None:
    if response.status_code == 200:
        response_200 = TOTPVerifySetupResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | TOTPVerifySetupResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: TOTPVerifySetupRequest,

) -> Response[HTTPValidationError | TOTPVerifySetupResponse]:
    """ Verify Setup 2Fa

     Verify TOTP setup with a code from the authenticator app and enable 2FA.

    Args:
        body (TOTPVerifySetupRequest): Request to verify and enable 2FA.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TOTPVerifySetupResponse]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    body: TOTPVerifySetupRequest,

) -> HTTPValidationError | TOTPVerifySetupResponse | None:
    """ Verify Setup 2Fa

     Verify TOTP setup with a code from the authenticator app and enable 2FA.

    Args:
        body (TOTPVerifySetupRequest): Request to verify and enable 2FA.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TOTPVerifySetupResponse
     """


    return sync_detailed(
        client=client,
body=body,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: TOTPVerifySetupRequest,

) -> Response[HTTPValidationError | TOTPVerifySetupResponse]:
    """ Verify Setup 2Fa

     Verify TOTP setup with a code from the authenticator app and enable 2FA.

    Args:
        body (TOTPVerifySetupRequest): Request to verify and enable 2FA.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TOTPVerifySetupResponse]
     """


    kwargs = _get_kwargs(
        body=body,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    body: TOTPVerifySetupRequest,

) -> HTTPValidationError | TOTPVerifySetupResponse | None:
    """ Verify Setup 2Fa

     Verify TOTP setup with a code from the authenticator app and enable 2FA.

    Args:
        body (TOTPVerifySetupRequest): Request to verify and enable 2FA.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TOTPVerifySetupResponse
     """


    return (await asyncio_detailed(
        client=client,
body=body,

    )).parsed
