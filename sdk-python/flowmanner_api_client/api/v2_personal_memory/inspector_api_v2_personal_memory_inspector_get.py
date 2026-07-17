from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.inspector_api_v2_personal_memory_inspector_get_response_inspector_api_v2_personal_memory_inspector_get import (
    InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    scope: None | str | Unset = UNSET,
    claim_type: None | str | Unset = UNSET,
    include_deleted: bool | Unset = False,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_scope: None | str | Unset
    if isinstance(scope, Unset):
        json_scope = UNSET
    else:
        json_scope = scope
    params["scope"] = json_scope

    json_claim_type: None | str | Unset
    if isinstance(claim_type, Unset):
        json_claim_type = UNSET
    else:
        json_claim_type = claim_type
    params["claim_type"] = json_claim_type

    params["include_deleted"] = include_deleted

    params["page"] = page

    params["per_page"] = per_page

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/personal_memory/inspector",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet
    | None
):
    if response.status_code == 200:
        response_200 = (
            InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet.from_dict(
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
    HTTPValidationError | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet
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
    scope: None | str | Unset = UNSET,
    claim_type: None | str | Unset = UNSET,
    include_deleted: bool | Unset = False,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> Response[
    HTTPValidationError | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet
]:
    """Inspector

    Args:
        scope (None | str | Unset):
        claim_type (None | str | Unset):
        include_deleted (bool | Unset):  Default: False.
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet]
    """

    kwargs = _get_kwargs(
        scope=scope,
        claim_type=claim_type,
        include_deleted=include_deleted,
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
    scope: None | str | Unset = UNSET,
    claim_type: None | str | Unset = UNSET,
    include_deleted: bool | Unset = False,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> (
    HTTPValidationError
    | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet
    | None
):
    """Inspector

    Args:
        scope (None | str | Unset):
        claim_type (None | str | Unset):
        include_deleted (bool | Unset):  Default: False.
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet
    """

    return sync_detailed(
        client=client,
        scope=scope,
        claim_type=claim_type,
        include_deleted=include_deleted,
        page=page,
        per_page=per_page,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    scope: None | str | Unset = UNSET,
    claim_type: None | str | Unset = UNSET,
    include_deleted: bool | Unset = False,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> Response[
    HTTPValidationError | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet
]:
    """Inspector

    Args:
        scope (None | str | Unset):
        claim_type (None | str | Unset):
        include_deleted (bool | Unset):  Default: False.
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet]
    """

    kwargs = _get_kwargs(
        scope=scope,
        claim_type=claim_type,
        include_deleted=include_deleted,
        page=page,
        per_page=per_page,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    scope: None | str | Unset = UNSET,
    claim_type: None | str | Unset = UNSET,
    include_deleted: bool | Unset = False,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> (
    HTTPValidationError
    | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet
    | None
):
    """Inspector

    Args:
        scope (None | str | Unset):
        claim_type (None | str | Unset):
        include_deleted (bool | Unset):  Default: False.
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | InspectorApiV2PersonalMemoryInspectorGetResponseInspectorApiV2PersonalMemoryInspectorGet
    """

    return (
        await asyncio_detailed(
            client=client,
            scope=scope,
            claim_type=claim_type,
            include_deleted=include_deleted,
            page=page,
            per_page=per_page,
        )
    ).parsed
