from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    featured: bool | None | Unset = UNSET,
    sort: str | Unset = "relevance",
    page: int | Unset = 1,
    per_page: int | Unset = 20,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

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

    json_q: None | str | Unset
    if isinstance(q, Unset):
        json_q = UNSET
    else:
        json_q = q
    params["q"] = json_q

    json_featured: bool | None | Unset
    if isinstance(featured, Unset):
        json_featured = UNSET
    else:
        json_featured = featured
    params["featured"] = json_featured

    params["sort"] = sort

    params["page"] = page

    params["per_page"] = per_page

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/marketplace/listings",
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
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    featured: bool | None | Unset = UNSET,
    sort: str | Unset = "relevance",
    page: int | Unset = 1,
    per_page: int | Unset = 20,
) -> Response[Any | HTTPValidationError]:
    """List Listings

     List marketplace listings with filtering, search, and pagination.

    Args:
        type_ (None | str | Unset): Filter by listing type: tool, capability, integration, agent
        category (None | str | Unset): Filter by category
        q (None | str | Unset): Search query
        featured (bool | None | Unset): Filter featured only
        sort (str | Unset): Sort: relevance, popularity, rating, newest, price_low, price_high
            Default: 'relevance'.
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        type_=type_,
        category=category,
        q=q,
        featured=featured,
        sort=sort,
        page=page,
        per_page=per_page,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    featured: bool | None | Unset = UNSET,
    sort: str | Unset = "relevance",
    page: int | Unset = 1,
    per_page: int | Unset = 20,
) -> Any | HTTPValidationError | None:
    """List Listings

     List marketplace listings with filtering, search, and pagination.

    Args:
        type_ (None | str | Unset): Filter by listing type: tool, capability, integration, agent
        category (None | str | Unset): Filter by category
        q (None | str | Unset): Search query
        featured (bool | None | Unset): Filter featured only
        sort (str | Unset): Sort: relevance, popularity, rating, newest, price_low, price_high
            Default: 'relevance'.
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        type_=type_,
        category=category,
        q=q,
        featured=featured,
        sort=sort,
        page=page,
        per_page=per_page,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    featured: bool | None | Unset = UNSET,
    sort: str | Unset = "relevance",
    page: int | Unset = 1,
    per_page: int | Unset = 20,
) -> Response[Any | HTTPValidationError]:
    """List Listings

     List marketplace listings with filtering, search, and pagination.

    Args:
        type_ (None | str | Unset): Filter by listing type: tool, capability, integration, agent
        category (None | str | Unset): Filter by category
        q (None | str | Unset): Search query
        featured (bool | None | Unset): Filter featured only
        sort (str | Unset): Sort: relevance, popularity, rating, newest, price_low, price_high
            Default: 'relevance'.
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        type_=type_,
        category=category,
        q=q,
        featured=featured,
        sort=sort,
        page=page,
        per_page=per_page,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    type_: None | str | Unset = UNSET,
    category: None | str | Unset = UNSET,
    q: None | str | Unset = UNSET,
    featured: bool | None | Unset = UNSET,
    sort: str | Unset = "relevance",
    page: int | Unset = 1,
    per_page: int | Unset = 20,
) -> Any | HTTPValidationError | None:
    """List Listings

     List marketplace listings with filtering, search, and pagination.

    Args:
        type_ (None | str | Unset): Filter by listing type: tool, capability, integration, agent
        category (None | str | Unset): Filter by category
        q (None | str | Unset): Search query
        featured (bool | None | Unset): Filter featured only
        sort (str | Unset): Sort: relevance, popularity, rating, newest, price_low, price_high
            Default: 'relevance'.
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 20.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            type_=type_,
            category=category,
            q=q,
            featured=featured,
            sort=sort,
            page=page,
            per_page=per_page,
        )
    ).parsed
