from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    claim_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/personal_memory/claims/{claim_id}/provenance".format(
            claim_id=quote(str(claim_id), safe=""),
        ),
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
    claim_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Any | HTTPValidationError]:
    r"""Claim Provenance

     Return the full provenance trace for a single claim (Epic 3.6).

    Answers \"Why does the agent believe X?\" by composing three data
    sources that already exist — this is pure exposure work, no new
    persistence:

    * ``claim`` — the ``PersonalMemoryClaim`` itself.
    * ``provenance`` — origin projection (source_type, source_id, the
      mission-specific ``source_mission_id`` convenience alias, created_at,
      confidence, importance, scope).
    * ``corrections`` — the durable ``memory_correction_events`` audit
      trail scoped to this claim (most-recent-first).
    * ``audit_summary`` — the T32 aggregate roll-up (event counts by type,
      first/last event) preserved so nothing regresses.

    Scope guardrail: every read is filtered by ``(user_id, workspace_id)``.
    A claim that isn't visible to the caller (cross-tenant, wrong user)
    surfaces as a 404 envelope — never a cross-tenant leak, and the
    correction/summary reads are only performed once the claim is proven
    visible.

    Args:
        claim_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        claim_id=claim_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    claim_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Any | HTTPValidationError | None:
    r"""Claim Provenance

     Return the full provenance trace for a single claim (Epic 3.6).

    Answers \"Why does the agent believe X?\" by composing three data
    sources that already exist — this is pure exposure work, no new
    persistence:

    * ``claim`` — the ``PersonalMemoryClaim`` itself.
    * ``provenance`` — origin projection (source_type, source_id, the
      mission-specific ``source_mission_id`` convenience alias, created_at,
      confidence, importance, scope).
    * ``corrections`` — the durable ``memory_correction_events`` audit
      trail scoped to this claim (most-recent-first).
    * ``audit_summary`` — the T32 aggregate roll-up (event counts by type,
      first/last event) preserved so nothing regresses.

    Scope guardrail: every read is filtered by ``(user_id, workspace_id)``.
    A claim that isn't visible to the caller (cross-tenant, wrong user)
    surfaces as a 404 envelope — never a cross-tenant leak, and the
    correction/summary reads are only performed once the claim is proven
    visible.

    Args:
        claim_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        claim_id=claim_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    claim_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[Any | HTTPValidationError]:
    r"""Claim Provenance

     Return the full provenance trace for a single claim (Epic 3.6).

    Answers \"Why does the agent believe X?\" by composing three data
    sources that already exist — this is pure exposure work, no new
    persistence:

    * ``claim`` — the ``PersonalMemoryClaim`` itself.
    * ``provenance`` — origin projection (source_type, source_id, the
      mission-specific ``source_mission_id`` convenience alias, created_at,
      confidence, importance, scope).
    * ``corrections`` — the durable ``memory_correction_events`` audit
      trail scoped to this claim (most-recent-first).
    * ``audit_summary`` — the T32 aggregate roll-up (event counts by type,
      first/last event) preserved so nothing regresses.

    Scope guardrail: every read is filtered by ``(user_id, workspace_id)``.
    A claim that isn't visible to the caller (cross-tenant, wrong user)
    surfaces as a 404 envelope — never a cross-tenant leak, and the
    correction/summary reads are only performed once the claim is proven
    visible.

    Args:
        claim_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        claim_id=claim_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    claim_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Any | HTTPValidationError | None:
    r"""Claim Provenance

     Return the full provenance trace for a single claim (Epic 3.6).

    Answers \"Why does the agent believe X?\" by composing three data
    sources that already exist — this is pure exposure work, no new
    persistence:

    * ``claim`` — the ``PersonalMemoryClaim`` itself.
    * ``provenance`` — origin projection (source_type, source_id, the
      mission-specific ``source_mission_id`` convenience alias, created_at,
      confidence, importance, scope).
    * ``corrections`` — the durable ``memory_correction_events`` audit
      trail scoped to this claim (most-recent-first).
    * ``audit_summary`` — the T32 aggregate roll-up (event counts by type,
      first/last event) preserved so nothing regresses.

    Scope guardrail: every read is filtered by ``(user_id, workspace_id)``.
    A claim that isn't visible to the caller (cross-tenant, wrong user)
    surfaces as a 404 envelope — never a cross-tenant leak, and the
    correction/summary reads are only performed once the claim is proven
    visible.

    Args:
        claim_id (UUID):

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
        )
    ).parsed
