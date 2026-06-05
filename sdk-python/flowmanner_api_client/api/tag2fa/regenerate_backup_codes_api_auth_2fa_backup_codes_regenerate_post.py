from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.totp_regenerate_backup_codes_request import (
    TOTPRegenerateBackupCodesRequest,
)
from ...models.totp_regenerate_response import TOTPRegenerateResponse
from ...types import Response


def _get_kwargs(
    *,
    body: TOTPRegenerateBackupCodesRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/auth/2fa/backup-codes/regenerate",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | TOTPRegenerateResponse | None:
    if response.status_code == 200:
        response_200 = TOTPRegenerateResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | TOTPRegenerateResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: TOTPRegenerateBackupCodesRequest,
) -> Response[HTTPValidationError | TOTPRegenerateResponse]:
    """Regenerate Backup Codes

     Regenerate backup codes. Requires password and a valid TOTP code.

    Args:
        body (TOTPRegenerateBackupCodesRequest): Request to regenerate backup codes.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TOTPRegenerateResponse]
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
    body: TOTPRegenerateBackupCodesRequest,
) -> HTTPValidationError | TOTPRegenerateResponse | None:
    """Regenerate Backup Codes

     Regenerate backup codes. Requires password and a valid TOTP code.

    Args:
        body (TOTPRegenerateBackupCodesRequest): Request to regenerate backup codes.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TOTPRegenerateResponse
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: TOTPRegenerateBackupCodesRequest,
) -> Response[HTTPValidationError | TOTPRegenerateResponse]:
    """Regenerate Backup Codes

     Regenerate backup codes. Requires password and a valid TOTP code.

    Args:
        body (TOTPRegenerateBackupCodesRequest): Request to regenerate backup codes.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TOTPRegenerateResponse]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: TOTPRegenerateBackupCodesRequest,
) -> HTTPValidationError | TOTPRegenerateResponse | None:
    """Regenerate Backup Codes

     Regenerate backup codes. Requires password and a valid TOTP code.

    Args:
        body (TOTPRegenerateBackupCodesRequest): Request to regenerate backup codes.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TOTPRegenerateResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
