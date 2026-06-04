from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.http_validation_error import HTTPValidationError
from ...models.listings_response import ListingsResponse
from ...types import UNSET, Unset
from typing import cast



def _get_kwargs(
    *,
    search: None | str | Unset = UNSET,
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version



    

    params: dict[str, Any] = {}

    json_search: None | str | Unset
    if isinstance(search, Unset):
        json_search = UNSET
    else:
        json_search = search
    params["search"] = json_search

    json_type_: None | str | Unset
    if isinstance(type_, Unset):
        json_type_ = UNSET
    else:
        json_type_ = type_
    params["type"] = json_type_

    json_category: None | str | Unset
    if isinstance(category, Unset):
        json_category = UNSET
    else:
        json_category = category
    params["category"] = json_category

    json_sort: None | str | Unset
    if isinstance(sort, Unset):
        json_sort = UNSET
    else:
        json_sort = sort
    params["sort"] = json_sort

    params["page"] = page

    params["per_page"] = per_page


    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}


    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/marketplace/listings",
        "params": params,
    }


    _kwargs["headers"] = headers
    return _kwargs



def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> HTTPValidationError | ListingsResponse | None:
    if response.status_code == 200:
        response_200 = ListingsResponse.from_dict(response.json())



        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())



        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Response[HTTPValidationError | ListingsResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | ListingsResponse]:
    """ List Listings

    Args:
        search (None | str | Unset):
        type_ (None | str | Unset):
        category (None | str | Unset):
        sort (None | str | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListingsResponse]
     """


    kwargs = _get_kwargs(
        search=search,
type_=type_,
category=category,
sort=sort,
page=page,
per_page=per_page,
accept_version=accept_version,

    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)

def sync(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | ListingsResponse | None:
    """ List Listings

    Args:
        search (None | str | Unset):
        type_ (None | str | Unset):
        category (None | str | Unset):
        sort (None | str | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListingsResponse
     """


    return sync_detailed(
        client=client,
search=search,
type_=type_,
category=category,
sort=sort,
page=page,
per_page=per_page,
accept_version=accept_version,

    ).parsed

async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> Response[HTTPValidationError | ListingsResponse]:
    """ List Listings

    Args:
        search (None | str | Unset):
        type_ (None | str | Unset):
        category (None | str | Unset):
        sort (None | str | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListingsResponse]
     """


    kwargs = _get_kwargs(
        search=search,
type_=type_,
category=category,
sort=sort,
page=page,
per_page=per_page,
accept_version=accept_version,

    )

    response = await client.get_async_httpx_client().request(
        **kwargs
    )

    return _build_response(client=client, response=response)

async def asyncio(
    *,
    client: AuthenticatedClient,
    search: None | str | Unset = UNSET,
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    sort: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 20,
    accept_version: str | Unset = 'v1',

) -> HTTPValidationError | ListingsResponse | None:
    """ List Listings

    Args:
        search (None | str | Unset):
        type_ (None | str | Unset):
        category (None | str | Unset):
        sort (None | str | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListingsResponse
     """


    return (await asyncio_detailed(
        client=client,
search=search,
type_=type_,
category=category,
sort=sort,
page=page,
per_page=per_page,
accept_version=accept_version,

    )).parsed
