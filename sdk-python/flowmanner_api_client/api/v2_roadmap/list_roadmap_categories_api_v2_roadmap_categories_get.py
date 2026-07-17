from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.list_roadmap_categories_api_v2_roadmap_categories_get_response_list_roadmap_categories_api_v2_roadmap_categories_get import (
    ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet,
)
from ...types import Response


def _get_kwargs() -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/roadmap/categories",
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet | None:
    if response.status_code == 200:
        response_200 = ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet.from_dict(
            response.json()
        )

        return response_200

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet]:
    """List Roadmap Categories

     Derived roadmap categories (auth-required).

    Aggregates `COUNT(*)` per non-null category over public items. Returns
    `{id, name, count}` matching the frontend `RoadmapCategoryOut` shape;
    `id` is the category slug itself (no dedicated table exists).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet]
    """

    kwargs = _get_kwargs()

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
) -> ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet | None:
    """List Roadmap Categories

     Derived roadmap categories (auth-required).

    Aggregates `COUNT(*)` per non-null category over public items. Returns
    `{id, name, count}` matching the frontend `RoadmapCategoryOut` shape;
    `id` is the category slug itself (no dedicated table exists).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet
    """

    return sync_detailed(
        client=client,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
) -> Response[ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet]:
    """List Roadmap Categories

     Derived roadmap categories (auth-required).

    Aggregates `COUNT(*)` per non-null category over public items. Returns
    `{id, name, count}` matching the frontend `RoadmapCategoryOut` shape;
    `id` is the category slug itself (no dedicated table exists).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet]
    """

    kwargs = _get_kwargs()

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
) -> ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet | None:
    """List Roadmap Categories

     Derived roadmap categories (auth-required).

    Aggregates `COUNT(*)` per non-null category over public items. Returns
    `{id, name, count}` matching the frontend `RoadmapCategoryOut` shape;
    `id` is the category slug itself (no dedicated table exists).

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ListRoadmapCategoriesApiV2RoadmapCategoriesGetResponseListRoadmapCategoriesApiV2RoadmapCategoriesGet
    """

    return (
        await asyncio_detailed(
            client=client,
        )
    ).parsed
