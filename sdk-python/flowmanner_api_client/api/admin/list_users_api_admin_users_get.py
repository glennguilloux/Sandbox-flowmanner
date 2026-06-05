from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.user_list_response import UserListResponse
from ...types import UNSET, Unset
from typing import cast


def _get_kwargs(
    *,
    page: int | Unset = 1,
    page_size: int | Unset = 20,
    role: None | str | Unset = UNSET,
    is_active: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    params: dict[str, Any] = {}

    params["page"] = page

    params["page_size"] = page_size

    json_role: None | str | Unset
    if isinstance(role, Unset):
        json_role = UNSET
    else:
        json_role = role
    params["role"] = json_role

    json_is_active: bool | None | Unset
    if isinstance(is_active, Unset):
        json_is_active = UNSET
    else:
        json_is_active = is_active
    params["is_active"] = json_is_active

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/admin/users",
        "params": params,
    }

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | UserListResponse | None:
    if response.status_code == 200:
        response_200 = UserListResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | UserListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    page_size: int | Unset = 20,
    role: None | str | Unset = UNSET,
    is_active: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | UserListResponse]:
    """List Users

    Args:
        page (int | Unset):  Default: 1.
        page_size (int | Unset):  Default: 20.
        role (None | str | Unset):
        is_active (bool | None | Unset):
        search (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserListResponse]
    """

    kwargs = _get_kwargs(
        page=page,
        page_size=page_size,
        role=role,
        is_active=is_active,
        search=search,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    page_size: int | Unset = 20,
    role: None | str | Unset = UNSET,
    is_active: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | UserListResponse | None:
    """List Users

    Args:
        page (int | Unset):  Default: 1.
        page_size (int | Unset):  Default: 20.
        role (None | str | Unset):
        is_active (bool | None | Unset):
        search (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserListResponse
    """

    return sync_detailed(
        client=client,
        page=page,
        page_size=page_size,
        role=role,
        is_active=is_active,
        search=search,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    page_size: int | Unset = 20,
    role: None | str | Unset = UNSET,
    is_active: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | UserListResponse]:
    """List Users

    Args:
        page (int | Unset):  Default: 1.
        page_size (int | Unset):  Default: 20.
        role (None | str | Unset):
        is_active (bool | None | Unset):
        search (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | UserListResponse]
    """

    kwargs = _get_kwargs(
        page=page,
        page_size=page_size,
        role=role,
        is_active=is_active,
        search=search,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    page_size: int | Unset = 20,
    role: None | str | Unset = UNSET,
    is_active: bool | None | Unset = UNSET,
    search: None | str | Unset = UNSET,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | UserListResponse | None:
    """List Users

    Args:
        page (int | Unset):  Default: 1.
        page_size (int | Unset):  Default: 20.
        role (None | str | Unset):
        is_active (bool | None | Unset):
        search (None | str | Unset):
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | UserListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            page=page,
            page_size=page_size,
            role=role,
            is_active=is_active,
            search=search,
            accept_version=accept_version,
        )
    ).parsed
