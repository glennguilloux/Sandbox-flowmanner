from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.tenant_member_update import TenantMemberUpdate
from ...types import Response, Unset


def _get_kwargs(
    tenant_id: str,
    member_id: str,
    *,
    body: TenantMemberUpdate,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "put",
        "url": "/api/tenants/{tenant_id}/members/{member_id}".format(
            tenant_id=quote(str(tenant_id), safe=""),
            member_id=quote(str(member_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

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
    member_id: str,
    *,
    client: AuthenticatedClient,
    body: TenantMemberUpdate,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError]:
    """Update Tenant Member

     Update a member's role in a tenant.

    Only tenant admins/owners or platform admins can update member roles.

    Args:
        tenant_id (str):
        member_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (TenantMemberUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tenant_id=tenant_id,
        member_id=member_id,
        body=body,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    tenant_id: str,
    member_id: str,
    *,
    client: AuthenticatedClient,
    body: TenantMemberUpdate,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | None:
    """Update Tenant Member

     Update a member's role in a tenant.

    Only tenant admins/owners or platform admins can update member roles.

    Args:
        tenant_id (str):
        member_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (TenantMemberUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError
    """

    return sync_detailed(
        tenant_id=tenant_id,
        member_id=member_id,
        client=client,
        body=body,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    tenant_id: str,
    member_id: str,
    *,
    client: AuthenticatedClient,
    body: TenantMemberUpdate,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError]:
    """Update Tenant Member

     Update a member's role in a tenant.

    Only tenant admins/owners or platform admins can update member roles.

    Args:
        tenant_id (str):
        member_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (TenantMemberUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError]
    """

    kwargs = _get_kwargs(
        tenant_id=tenant_id,
        member_id=member_id,
        body=body,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    tenant_id: str,
    member_id: str,
    *,
    client: AuthenticatedClient,
    body: TenantMemberUpdate,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | None:
    """Update Tenant Member

     Update a member's role in a tenant.

    Only tenant admins/owners or platform admins can update member roles.

    Args:
        tenant_id (str):
        member_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (TenantMemberUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError
    """

    return (
        await asyncio_detailed(
            tenant_id=tenant_id,
            member_id=member_id,
            client=client,
            body=body,
            accept_version=accept_version,
        )
    ).parsed
