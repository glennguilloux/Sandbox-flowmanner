from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    status: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    sort_by: str | Unset = "started_at",
    sort_order: str | Unset = "desc",
    date_from: None | str | Unset = UNSET,
    date_to: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    params["page"] = page

    params["per_page"] = per_page

    json_status: None | str | Unset
    if isinstance(status, Unset):
        json_status = UNSET
    else:
        json_status = status
    params["status"] = json_status

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search

    params["sort_by"] = sort_by

    params["sort_order"] = sort_order

    json_date_from: None | str | Unset
    if isinstance(date_from, Unset):
        json_date_from = UNSET
    else:
        json_date_from = date_from
    params["date_from"] = json_date_from

    json_date_to: None | str | Unset
    if isinstance(date_to, Unset):
        json_date_to = UNSET
    else:
        json_date_to = date_to
    params["date_to"] = json_date_to

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/dashboard/missions",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Any | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = response.json()
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
) -> Response[Any | HTTPValidationError]:
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
    per_page: int | Unset = 20,
    status: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    sort_by: str | Unset = "started_at",
    sort_order: str | Unset = "desc",
    date_from: None | str | Unset = UNSET,
    date_to: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List Missions

     Paginated mission history for the current user.

    Args:
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        status (None | str | Unset): Filter by mission status
        search (None | str | Unset): Search by title
        sort_by (str | Unset):  Default: 'started_at'.
        sort_order (str | Unset):  Default: 'desc'.
        date_from (None | str | Unset): ISO date filter start
        date_to (None | str | Unset): ISO date filter end

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        page=page,
        per_page=per_page,
        status=status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        date_from=date_from,
        date_to=date_to,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    status: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    sort_by: str | Unset = "started_at",
    sort_order: str | Unset = "desc",
    date_from: None | str | Unset = UNSET,
    date_to: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List Missions

     Paginated mission history for the current user.

    Args:
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        status (None | str | Unset): Filter by mission status
        search (None | str | Unset): Search by title
        sort_by (str | Unset):  Default: 'started_at'.
        sort_order (str | Unset):  Default: 'desc'.
        date_from (None | str | Unset): ISO date filter start
        date_to (None | str | Unset): ISO date filter end

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        page=page,
        per_page=per_page,
        status=status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        date_from=date_from,
        date_to=date_to,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    status: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    sort_by: str | Unset = "started_at",
    sort_order: str | Unset = "desc",
    date_from: None | str | Unset = UNSET,
    date_to: None | str | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """List Missions

     Paginated mission history for the current user.

    Args:
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        status (None | str | Unset): Filter by mission status
        search (None | str | Unset): Search by title
        sort_by (str | Unset):  Default: 'started_at'.
        sort_order (str | Unset):  Default: 'desc'.
        date_from (None | str | Unset): ISO date filter start
        date_to (None | str | Unset): ISO date filter end

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        page=page,
        per_page=per_page,
        status=status,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        date_from=date_from,
        date_to=date_to,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    status: None | str | Unset = UNSET,
    search: None | str | Unset = UNSET,
    sort_by: str | Unset = "started_at",
    sort_order: str | Unset = "desc",
    date_from: None | str | Unset = UNSET,
    date_to: None | str | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """List Missions

     Paginated mission history for the current user.

    Args:
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        status (None | str | Unset): Filter by mission status
        search (None | str | Unset): Search by title
        sort_by (str | Unset):  Default: 'started_at'.
        sort_order (str | Unset):  Default: 'desc'.
        date_from (None | str | Unset): ISO date filter start
        date_to (None | str | Unset): ISO date filter end

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            page=page,
            per_page=per_page,
            status=status,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            date_from=date_from,
            date_to=date_to,
        )
    ).parsed
