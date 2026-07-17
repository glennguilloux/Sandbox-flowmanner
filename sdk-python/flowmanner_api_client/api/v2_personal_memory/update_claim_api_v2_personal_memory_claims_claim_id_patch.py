from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.personal_memory_claim_update import PersonalMemoryClaimUpdate
from ...types import Response


def _get_kwargs(
    claim_id: UUID,
    *,
    body: PersonalMemoryClaimUpdate,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/v2/personal_memory/claims/{claim_id}".format(
            claim_id=quote(str(claim_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
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
    claim_id: UUID,
    *,
    client: AuthenticatedClient,
    body: PersonalMemoryClaimUpdate,
) -> Response[Any | HTTPValidationError]:
    """Update Claim

    Args:
        claim_id (UUID):
        body (PersonalMemoryClaimUpdate): Request body for ``PATCH /claims/{id}`` (PATCH
            semantics).

            All fields Optional. Fields NOT in this schema (user_id,
            workspace_id, id, claim_type, scope, source_type, created_at,
            updated_at) cannot be changed via PATCH — ``extra="forbid"``
            raises 422 if a client tries.

            Note: ``claim_type`` / ``scope`` / ``source_type`` are
            intentionally NOT editable via PATCH because changing a claim's
            taxonomy would invalidate provenance. Re-create the claim if you
            need to reclassify.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        claim_id=claim_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    claim_id: UUID,
    *,
    client: AuthenticatedClient,
    body: PersonalMemoryClaimUpdate,
) -> Any | HTTPValidationError | None:
    """Update Claim

    Args:
        claim_id (UUID):
        body (PersonalMemoryClaimUpdate): Request body for ``PATCH /claims/{id}`` (PATCH
            semantics).

            All fields Optional. Fields NOT in this schema (user_id,
            workspace_id, id, claim_type, scope, source_type, created_at,
            updated_at) cannot be changed via PATCH — ``extra="forbid"``
            raises 422 if a client tries.

            Note: ``claim_type`` / ``scope`` / ``source_type`` are
            intentionally NOT editable via PATCH because changing a claim's
            taxonomy would invalidate provenance. Re-create the claim if you
            need to reclassify.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        claim_id=claim_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    claim_id: UUID,
    *,
    client: AuthenticatedClient,
    body: PersonalMemoryClaimUpdate,
) -> Response[Any | HTTPValidationError]:
    """Update Claim

    Args:
        claim_id (UUID):
        body (PersonalMemoryClaimUpdate): Request body for ``PATCH /claims/{id}`` (PATCH
            semantics).

            All fields Optional. Fields NOT in this schema (user_id,
            workspace_id, id, claim_type, scope, source_type, created_at,
            updated_at) cannot be changed via PATCH — ``extra="forbid"``
            raises 422 if a client tries.

            Note: ``claim_type`` / ``scope`` / ``source_type`` are
            intentionally NOT editable via PATCH because changing a claim's
            taxonomy would invalidate provenance. Re-create the claim if you
            need to reclassify.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        claim_id=claim_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    claim_id: UUID,
    *,
    client: AuthenticatedClient,
    body: PersonalMemoryClaimUpdate,
) -> Any | HTTPValidationError | None:
    """Update Claim

    Args:
        claim_id (UUID):
        body (PersonalMemoryClaimUpdate): Request body for ``PATCH /claims/{id}`` (PATCH
            semantics).

            All fields Optional. Fields NOT in this schema (user_id,
            workspace_id, id, claim_type, scope, source_type, created_at,
            updated_at) cannot be changed via PATCH — ``extra="forbid"``
            raises 422 if a client tries.

            Note: ``claim_type`` / ``scope`` / ``source_type`` are
            intentionally NOT editable via PATCH because changing a claim's
            taxonomy would invalidate provenance. Re-create the claim if you
            need to reclassify.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            claim_id=claim_id,
            client=client,
            body=body,
        )
    ).parsed
