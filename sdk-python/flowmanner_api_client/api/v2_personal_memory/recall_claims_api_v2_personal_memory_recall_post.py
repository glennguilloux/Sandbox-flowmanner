from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.personal_memory_recall_request import PersonalMemoryRecallRequest
from ...models.recall_claims_api_v2_personal_memory_recall_post_response_recall_claims_api_v2_personal_memory_recall_post import (
    RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost,
)
from ...types import Response


def _get_kwargs(
    *,
    body: PersonalMemoryRecallRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/personal_memory/recall",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost
    | None
):
    if response.status_code == 200:
        response_200 = (
            RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost.from_dict(
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
    HTTPValidationError | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost
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
    body: PersonalMemoryRecallRequest,
) -> Response[
    HTTPValidationError | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost
]:
    """Recall Claims

    Args:
        body (PersonalMemoryRecallRequest): Request body for ``POST /claims/recall``.

            ``query`` is matched against (subject, predicate) via a simple
            case-insensitive substring search in T19. T20+ will replace this
            with semantic search via embeddings.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    body: PersonalMemoryRecallRequest,
) -> (
    HTTPValidationError
    | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost
    | None
):
    """Recall Claims

    Args:
        body (PersonalMemoryRecallRequest): Request body for ``POST /claims/recall``.

            ``query`` is matched against (subject, predicate) via a simple
            case-insensitive substring search in T19. T20+ will replace this
            with semantic search via embeddings.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: PersonalMemoryRecallRequest,
) -> Response[
    HTTPValidationError | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost
]:
    """Recall Claims

    Args:
        body (PersonalMemoryRecallRequest): Request body for ``POST /claims/recall``.

            ``query`` is matched against (subject, predicate) via a simple
            case-insensitive substring search in T19. T20+ will replace this
            with semantic search via embeddings.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: PersonalMemoryRecallRequest,
) -> (
    HTTPValidationError
    | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost
    | None
):
    """Recall Claims

    Args:
        body (PersonalMemoryRecallRequest): Request body for ``POST /claims/recall``.

            ``query`` is matched against (subject, predicate) via a simple
            case-insensitive substring search in T19. T20+ will replace this
            with semantic search via embeddings.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RecallClaimsApiV2PersonalMemoryRecallPostResponseRecallClaimsApiV2PersonalMemoryRecallPost
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
