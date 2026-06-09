from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.delegation_list_response import DelegationListResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Unset
from typing import cast


def _get_kwargs(
    *,
    delegator_id: int | None | Unset = UNSET,
    delegatee_id: int | None | Unset = UNSET,
    tenant_id: None | str | Unset = UNSET,
    active_only: bool | Unset = True,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    params: dict[str, Any] = {}

    json_delegator_id: int | None | Unset
    if isinstance(delegator_id, Unset):
        json_delegator_id = UNSET
    else:
        json_delegator_id = delegator_id
    params["delegator_id"] = json_delegator_id

    json_delegatee_id: int | None | Unset
    if isinstance(delegatee_id, Unset):
        json_delegatee_id = UNSET
    else:
        json_delegatee_id = delegatee_id
    params["delegatee_id"] = json_delegatee_id

    json_tenant_id: None | str | Unset
    if isinstance(tenant_id, Unset):
        json_tenant_id = UNSET
    else:
        json_tenant_id = tenant_id
    params["tenant_id"] = json_tenant_id

    params["active_only"] = active_only

    params["offset"] = offset

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/delegations",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DelegationListResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DelegationListResponse.from_dict(response.json())

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
) -> Response[DelegationListResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    delegator_id: int | None | Unset = UNSET,
    delegatee_id: int | None | Unset = UNSET,
    tenant_id: None | str | Unset = UNSET,
    active_only: bool | Unset = True,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> Response[DelegationListResponse | HTTPValidationError]:
    """List All Delegations

     List delegations with optional filters.

    Users can see delegations where they are the delegator or delegatee.
    Admins can see all delegations.

    Args:
        delegator_id (int | None | Unset): Filter by delegator user ID
        delegatee_id (int | None | Unset): Filter by delegatee user ID
        tenant_id (None | str | Unset): Filter by tenant ID
        active_only (bool | Unset): Only return active delegations Default: True.
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DelegationListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        delegator_id=delegator_id,
        delegatee_id=delegatee_id,
        tenant_id=tenant_id,
        active_only=active_only,
        offset=offset,
        limit=limit,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    delegator_id: int | None | Unset = UNSET,
    delegatee_id: int | None | Unset = UNSET,
    tenant_id: None | str | Unset = UNSET,
    active_only: bool | Unset = True,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> DelegationListResponse | HTTPValidationError | None:
    """List All Delegations

     List delegations with optional filters.

    Users can see delegations where they are the delegator or delegatee.
    Admins can see all delegations.

    Args:
        delegator_id (int | None | Unset): Filter by delegator user ID
        delegatee_id (int | None | Unset): Filter by delegatee user ID
        tenant_id (None | str | Unset): Filter by tenant ID
        active_only (bool | Unset): Only return active delegations Default: True.
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DelegationListResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        delegator_id=delegator_id,
        delegatee_id=delegatee_id,
        tenant_id=tenant_id,
        active_only=active_only,
        offset=offset,
        limit=limit,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    delegator_id: int | None | Unset = UNSET,
    delegatee_id: int | None | Unset = UNSET,
    tenant_id: None | str | Unset = UNSET,
    active_only: bool | Unset = True,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> Response[DelegationListResponse | HTTPValidationError]:
    """List All Delegations

     List delegations with optional filters.

    Users can see delegations where they are the delegator or delegatee.
    Admins can see all delegations.

    Args:
        delegator_id (int | None | Unset): Filter by delegator user ID
        delegatee_id (int | None | Unset): Filter by delegatee user ID
        tenant_id (None | str | Unset): Filter by tenant ID
        active_only (bool | Unset): Only return active delegations Default: True.
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DelegationListResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        delegator_id=delegator_id,
        delegatee_id=delegatee_id,
        tenant_id=tenant_id,
        active_only=active_only,
        offset=offset,
        limit=limit,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    delegator_id: int | None | Unset = UNSET,
    delegatee_id: int | None | Unset = UNSET,
    tenant_id: None | str | Unset = UNSET,
    active_only: bool | Unset = True,
    offset: int | Unset = 0,
    limit: int | Unset = 50,
    accept_version: str | Unset = "v1",
) -> DelegationListResponse | HTTPValidationError | None:
    """List All Delegations

     List delegations with optional filters.

    Users can see delegations where they are the delegator or delegatee.
    Admins can see all delegations.

    Args:
        delegator_id (int | None | Unset): Filter by delegator user ID
        delegatee_id (int | None | Unset): Filter by delegatee user ID
        tenant_id (None | str | Unset): Filter by tenant ID
        active_only (bool | Unset): Only return active delegations Default: True.
        offset (int | Unset):  Default: 0.
        limit (int | Unset):  Default: 50.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DelegationListResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            delegator_id=delegator_id,
            delegatee_id=delegatee_id,
            tenant_id=tenant_id,
            active_only=active_only,
            offset=offset,
            limit=limit,
            accept_version=accept_version,
        )
    ).parsed
