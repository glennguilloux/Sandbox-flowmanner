from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.list_conflicts_api_v2_personal_memory_conflicts_get_response_list_conflicts_api_v2_personal_memory_conflicts_get import (
    ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    scope: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_scope: None | str | Unset
    if isinstance(scope, Unset):
        json_scope = UNSET
    else:
        json_scope = scope
    params["scope"] = json_scope

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/personal_memory/conflicts",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet
    | None
):
    if response.status_code == 200:
        response_200 = (
            ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet.from_dict(
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
    HTTPValidationError
    | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet
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
) -> Response[
    HTTPValidationError
    | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet
]:
    """List Conflicts

     Surface conflicting live claims for the Memory Inspector.

    Returns only groups of claims that conflict on the same ``(subject,
    predicate)`` with a differing ``object``. Each group carries the
    deterministic winner (claim-type precedence > source priority > recency >
    confidence) plus the losers with an explainable ``superseded_because``.

    **Never deletes or merges** — surfacing only (per the 2.3 policy). Always
    scoped to ``(user_id, workspace_id)``.

    Args:
        scope (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet]
    """

    kwargs = _get_kwargs(
        scope=scope,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    scope: None | str | Unset = UNSET,
) -> (
    HTTPValidationError
    | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet
    | None
):
    """List Conflicts

     Surface conflicting live claims for the Memory Inspector.

    Returns only groups of claims that conflict on the same ``(subject,
    predicate)`` with a differing ``object``. Each group carries the
    deterministic winner (claim-type precedence > source priority > recency >
    confidence) plus the losers with an explainable ``superseded_because``.

    **Never deletes or merges** — surfacing only (per the 2.3 policy). Always
    scoped to ``(user_id, workspace_id)``.

    Args:
        scope (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet
    """

    return sync_detailed(
        client=client,
        scope=scope,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    scope: None | str | Unset = UNSET,
) -> Response[
    HTTPValidationError
    | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet
]:
    """List Conflicts

     Surface conflicting live claims for the Memory Inspector.

    Returns only groups of claims that conflict on the same ``(subject,
    predicate)`` with a differing ``object``. Each group carries the
    deterministic winner (claim-type precedence > source priority > recency >
    confidence) plus the losers with an explainable ``superseded_because``.

    **Never deletes or merges** — surfacing only (per the 2.3 policy). Always
    scoped to ``(user_id, workspace_id)``.

    Args:
        scope (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet]
    """

    kwargs = _get_kwargs(
        scope=scope,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    scope: None | str | Unset = UNSET,
) -> (
    HTTPValidationError
    | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet
    | None
):
    """List Conflicts

     Surface conflicting live claims for the Memory Inspector.

    Returns only groups of claims that conflict on the same ``(subject,
    predicate)`` with a differing ``object``. Each group carries the
    deterministic winner (claim-type precedence > source priority > recency >
    confidence) plus the losers with an explainable ``superseded_because``.

    **Never deletes or merges** — surfacing only (per the 2.3 policy). Always
    scoped to ``(user_id, workspace_id)``.

    Args:
        scope (None | str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListConflictsApiV2PersonalMemoryConflictsGetResponseListConflictsApiV2PersonalMemoryConflictsGet
    """

    return (
        await asyncio_detailed(
            client=client,
            scope=scope,
        )
    ).parsed
