from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    tenant_id: str,
    *,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    params: dict[str, Any] = {}

    params["offset"] = offset

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/tenants/{tenant_id}/members".format(
            tenant_id=quote(str(tenant_id), safe=""),
        ),
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | None:
    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    tenant_id: str,
    *,
    client: AuthenticatedClient,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError]:
    """List Tenant Members

     List all members of a tenant.

    Args:
        tenant_id (str):
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tenant_id=tenant_id,
        offset=offset,
        limit=limit,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    tenant_id: str,
    *,
    client: AuthenticatedClient,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | None:
    """List Tenant Members

     List all members of a tenant.

    Args:
        tenant_id (str):
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError
    """

    return sync_detailed(
        tenant_id=tenant_id,
        client=client,
        offset=offset,
        limit=limit,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    tenant_id: str,
    *,
    client: AuthenticatedClient,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError]:
    """List Tenant Members

     List all members of a tenant.

    Args:
        tenant_id (str):
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tenant_id=tenant_id,
        offset=offset,
        limit=limit,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    tenant_id: str,
    *,
    client: AuthenticatedClient,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | None:
    """List Tenant Members

     List all members of a tenant.

    Args:
        tenant_id (str):
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError
    """

    return (
        await asyncio_detailed(
            tenant_id=tenant_id,
            client=client,
            offset=offset,
            limit=limit,
            accept_version=accept_version,
        )
    ).parsed
