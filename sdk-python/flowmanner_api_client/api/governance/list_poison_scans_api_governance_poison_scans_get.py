from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.list_poison_scans_api_governance_poison_scans_get_response_list_poison_scans_api_governance_poison_scans_get import (
    ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet,
)
from ...models.list_poison_scans_api_governance_poison_scans_get_source_5 import (
    ListPoisonScansApiGovernancePoisonScansGetSource5,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    source: ListPoisonScansApiGovernancePoisonScansGetSource5
    | Unset = ListPoisonScansApiGovernancePoisonScansGetSource5.ALL,
    page: int | Unset = 1,
    page_size: int | Unset = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_source: str | Unset = UNSET
    if not isinstance(source, Unset):
        json_source = source.value

    params["source"] = json_source

    params["page"] = page

    params["page_size"] = page_size

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/governance/poison-scans",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet
    | None
):
    if response.status_code == 200:
        response_200 = (
            ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet.from_dict(
                response.json()
            )
        )

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
) -> Response[
    HTTPValidationError | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    source: ListPoisonScansApiGovernancePoisonScansGetSource5
    | Unset = ListPoisonScansApiGovernancePoisonScansGetSource5.ALL,
    page: int | Unset = 1,
    page_size: int | Unset = 50,
) -> Response[
    HTTPValidationError | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet
]:
    """List Poison Scans

     Return poison-scan flagged items with severity + provenance.

    Covers BOTH ``pending_writes`` (live) and ``personal_memory_claims``
    (retro) sources. Filtering + pagination are pushed to the database: the
    flagged verdict is matched by JSONB containment (``meta @> {poison_scan:
    {flagged: true}}``) and paging uses real ``LIMIT``/``OFFSET`` so we never
    load the full table into Python.

    Args:
        source (ListPoisonScansApiGovernancePoisonScansGetSource5 | Unset): Filter by verdict
            source: live|retro|all Default: ListPoisonScansApiGovernancePoisonScansGetSource5.ALL.
        page (int | Unset): 1-based page number Default: 1.
        page_size (int | Unset): Rows per page Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet]
    """

    kwargs = _get_kwargs(
        source=source,
        page=page,
        page_size=page_size,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    source: ListPoisonScansApiGovernancePoisonScansGetSource5
    | Unset = ListPoisonScansApiGovernancePoisonScansGetSource5.ALL,
    page: int | Unset = 1,
    page_size: int | Unset = 50,
) -> (
    HTTPValidationError
    | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet
    | None
):
    """List Poison Scans

     Return poison-scan flagged items with severity + provenance.

    Covers BOTH ``pending_writes`` (live) and ``personal_memory_claims``
    (retro) sources. Filtering + pagination are pushed to the database: the
    flagged verdict is matched by JSONB containment (``meta @> {poison_scan:
    {flagged: true}}``) and paging uses real ``LIMIT``/``OFFSET`` so we never
    load the full table into Python.

    Args:
        source (ListPoisonScansApiGovernancePoisonScansGetSource5 | Unset): Filter by verdict
            source: live|retro|all Default: ListPoisonScansApiGovernancePoisonScansGetSource5.ALL.
        page (int | Unset): 1-based page number Default: 1.
        page_size (int | Unset): Rows per page Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet
    """

    return sync_detailed(
        client=client,
        source=source,
        page=page,
        page_size=page_size,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    source: ListPoisonScansApiGovernancePoisonScansGetSource5
    | Unset = ListPoisonScansApiGovernancePoisonScansGetSource5.ALL,
    page: int | Unset = 1,
    page_size: int | Unset = 50,
) -> Response[
    HTTPValidationError | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet
]:
    """List Poison Scans

     Return poison-scan flagged items with severity + provenance.

    Covers BOTH ``pending_writes`` (live) and ``personal_memory_claims``
    (retro) sources. Filtering + pagination are pushed to the database: the
    flagged verdict is matched by JSONB containment (``meta @> {poison_scan:
    {flagged: true}}``) and paging uses real ``LIMIT``/``OFFSET`` so we never
    load the full table into Python.

    Args:
        source (ListPoisonScansApiGovernancePoisonScansGetSource5 | Unset): Filter by verdict
            source: live|retro|all Default: ListPoisonScansApiGovernancePoisonScansGetSource5.ALL.
        page (int | Unset): 1-based page number Default: 1.
        page_size (int | Unset): Rows per page Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet]
    """

    kwargs = _get_kwargs(
        source=source,
        page=page,
        page_size=page_size,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    source: ListPoisonScansApiGovernancePoisonScansGetSource5
    | Unset = ListPoisonScansApiGovernancePoisonScansGetSource5.ALL,
    page: int | Unset = 1,
    page_size: int | Unset = 50,
) -> (
    HTTPValidationError
    | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet
    | None
):
    """List Poison Scans

     Return poison-scan flagged items with severity + provenance.

    Covers BOTH ``pending_writes`` (live) and ``personal_memory_claims``
    (retro) sources. Filtering + pagination are pushed to the database: the
    flagged verdict is matched by JSONB containment (``meta @> {poison_scan:
    {flagged: true}}``) and paging uses real ``LIMIT``/``OFFSET`` so we never
    load the full table into Python.

    Args:
        source (ListPoisonScansApiGovernancePoisonScansGetSource5 | Unset): Filter by verdict
            source: live|retro|all Default: ListPoisonScansApiGovernancePoisonScansGetSource5.ALL.
        page (int | Unset): 1-based page number Default: 1.
        page_size (int | Unset): Rows per page Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListPoisonScansApiGovernancePoisonScansGetResponseListPoisonScansApiGovernancePoisonScansGet
    """

    return (
        await asyncio_detailed(
            client=client,
            source=source,
            page=page,
            page_size=page_size,
        )
    ).parsed
