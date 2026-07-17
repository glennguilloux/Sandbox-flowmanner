from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.reindex_qdrant_api_admin_reindex_post_source_2 import ReindexQdrantApiAdminReindexPostSource2
from ...models.reindex_response import ReindexResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    source: ReindexQdrantApiAdminReindexPostSource2 | Unset = ReindexQdrantApiAdminReindexPostSource2.DB,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_source: str | Unset = UNSET
    if not isinstance(source, Unset):
        json_source = source.value

    params["source"] = json_source

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/admin/reindex",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | ReindexResponse | None:
    if response.status_code == 200:
        response_200 = ReindexResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | ReindexResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    source: ReindexQdrantApiAdminReindexPostSource2 | Unset = ReindexQdrantApiAdminReindexPostSource2.DB,
) -> Response[HTTPValidationError | ReindexResponse]:
    """Reindex Qdrant

     Rebuild the Qdrant vector index from the canonical data source.

    - ``source=db`` (default): reads tools + capabilities directly from
      ``tools_catalog`` and ``capabilities_catalog`` tables.
    - ``source=registry``: reads from the in-memory ``ToolRegistry``
      (same as startup hydration).

    Args:
        source (ReindexQdrantApiAdminReindexPostSource2 | Unset): 'db' to rebuild from Postgres
            tables, 'registry' to rebuild from in-memory ToolRegistry Default:
            ReindexQdrantApiAdminReindexPostSource2.DB.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ReindexResponse]
    """

    kwargs = _get_kwargs(
        source=source,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    source: ReindexQdrantApiAdminReindexPostSource2 | Unset = ReindexQdrantApiAdminReindexPostSource2.DB,
) -> HTTPValidationError | ReindexResponse | None:
    """Reindex Qdrant

     Rebuild the Qdrant vector index from the canonical data source.

    - ``source=db`` (default): reads tools + capabilities directly from
      ``tools_catalog`` and ``capabilities_catalog`` tables.
    - ``source=registry``: reads from the in-memory ``ToolRegistry``
      (same as startup hydration).

    Args:
        source (ReindexQdrantApiAdminReindexPostSource2 | Unset): 'db' to rebuild from Postgres
            tables, 'registry' to rebuild from in-memory ToolRegistry Default:
            ReindexQdrantApiAdminReindexPostSource2.DB.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ReindexResponse
    """

    return sync_detailed(
        client=client,
        source=source,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    source: ReindexQdrantApiAdminReindexPostSource2 | Unset = ReindexQdrantApiAdminReindexPostSource2.DB,
) -> Response[HTTPValidationError | ReindexResponse]:
    """Reindex Qdrant

     Rebuild the Qdrant vector index from the canonical data source.

    - ``source=db`` (default): reads tools + capabilities directly from
      ``tools_catalog`` and ``capabilities_catalog`` tables.
    - ``source=registry``: reads from the in-memory ``ToolRegistry``
      (same as startup hydration).

    Args:
        source (ReindexQdrantApiAdminReindexPostSource2 | Unset): 'db' to rebuild from Postgres
            tables, 'registry' to rebuild from in-memory ToolRegistry Default:
            ReindexQdrantApiAdminReindexPostSource2.DB.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ReindexResponse]
    """

    kwargs = _get_kwargs(
        source=source,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    source: ReindexQdrantApiAdminReindexPostSource2 | Unset = ReindexQdrantApiAdminReindexPostSource2.DB,
) -> HTTPValidationError | ReindexResponse | None:
    """Reindex Qdrant

     Rebuild the Qdrant vector index from the canonical data source.

    - ``source=db`` (default): reads tools + capabilities directly from
      ``tools_catalog`` and ``capabilities_catalog`` tables.
    - ``source=registry``: reads from the in-memory ``ToolRegistry``
      (same as startup hydration).

    Args:
        source (ReindexQdrantApiAdminReindexPostSource2 | Unset): 'db' to rebuild from Postgres
            tables, 'registry' to rebuild from in-memory ToolRegistry Default:
            ReindexQdrantApiAdminReindexPostSource2.DB.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ReindexResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            source=source,
        )
    ).parsed
