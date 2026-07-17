from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.list_corrections_api_v2_personal_memory_corrections_get_response_list_corrections_api_v2_personal_memory_corrections_get import (
    ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet,
)
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    event_type: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_event_type: None | str | Unset
    if isinstance(event_type, Unset):
        json_event_type = UNSET
    else:
        json_event_type = event_type
    params["event_type"] = json_event_type

    params["page"] = page

    params["per_page"] = per_page

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/personal_memory/corrections",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet
    | None
):
    if response.status_code == 200:
        response_200 = ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet.from_dict(
            response.json()
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
    | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet
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
    event_type: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> Response[
    HTTPValidationError
    | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet
]:
    r"""List Corrections

     Return the durable ``memory_correction_events`` audit trail.

    GOV-1.6 closes the feedback loop read-side: the write path has been
    wired since GOV-1.4 (``PersonalMemoryService._safe_audit`` →
    ``MemoryCorrectionService``) but nothing ever surfaced it to the
    Inspector. This endpoint exposes the same privacy trail that every
    memory op / approval decision / dropped candidate writes to, so the
    corrections are finally readable — satisfying the C3 \"corrections are
    wired, not just written\" acceptance criterion.

    ``drop`` events (GOV-1.6 / C5) are dropped extraction candidates:
    ``claim_id`` is ``None`` and the candidate shape (claim_type / scope /
    confidence) lives in ``details``. Filter with ``?event_type=drop`` to
    see only calibration drops.

    Always scoped to ``(user_id, workspace_id)`` (the workspace isolation
    guardrail). A bad ``event_type`` surfaces as a 422 (raised by the
    service).

    Args:
        event_type (None | str | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet]
    """

    kwargs = _get_kwargs(
        event_type=event_type,
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
    event_type: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> (
    HTTPValidationError
    | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet
    | None
):
    r"""List Corrections

     Return the durable ``memory_correction_events`` audit trail.

    GOV-1.6 closes the feedback loop read-side: the write path has been
    wired since GOV-1.4 (``PersonalMemoryService._safe_audit`` →
    ``MemoryCorrectionService``) but nothing ever surfaced it to the
    Inspector. This endpoint exposes the same privacy trail that every
    memory op / approval decision / dropped candidate writes to, so the
    corrections are finally readable — satisfying the C3 \"corrections are
    wired, not just written\" acceptance criterion.

    ``drop`` events (GOV-1.6 / C5) are dropped extraction candidates:
    ``claim_id`` is ``None`` and the candidate shape (claim_type / scope /
    confidence) lives in ``details``. Filter with ``?event_type=drop`` to
    see only calibration drops.

    Always scoped to ``(user_id, workspace_id)`` (the workspace isolation
    guardrail). A bad ``event_type`` surfaces as a 422 (raised by the
    service).

    Args:
        event_type (None | str | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet
    """

    return sync_detailed(
        client=client,
        event_type=event_type,
        page=page,
        per_page=per_page,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    event_type: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> Response[
    HTTPValidationError
    | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet
]:
    r"""List Corrections

     Return the durable ``memory_correction_events`` audit trail.

    GOV-1.6 closes the feedback loop read-side: the write path has been
    wired since GOV-1.4 (``PersonalMemoryService._safe_audit`` →
    ``MemoryCorrectionService``) but nothing ever surfaced it to the
    Inspector. This endpoint exposes the same privacy trail that every
    memory op / approval decision / dropped candidate writes to, so the
    corrections are finally readable — satisfying the C3 \"corrections are
    wired, not just written\" acceptance criterion.

    ``drop`` events (GOV-1.6 / C5) are dropped extraction candidates:
    ``claim_id`` is ``None`` and the candidate shape (claim_type / scope /
    confidence) lives in ``details``. Filter with ``?event_type=drop`` to
    see only calibration drops.

    Always scoped to ``(user_id, workspace_id)`` (the workspace isolation
    guardrail). A bad ``event_type`` surfaces as a 422 (raised by the
    service).

    Args:
        event_type (None | str | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet]
    """

    kwargs = _get_kwargs(
        event_type=event_type,
        page=page,
        per_page=per_page,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    event_type: None | str | Unset = UNSET,
    page: int | Unset = 1,
    per_page: int | Unset = 50,
) -> (
    HTTPValidationError
    | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet
    | None
):
    r"""List Corrections

     Return the durable ``memory_correction_events`` audit trail.

    GOV-1.6 closes the feedback loop read-side: the write path has been
    wired since GOV-1.4 (``PersonalMemoryService._safe_audit`` →
    ``MemoryCorrectionService``) but nothing ever surfaced it to the
    Inspector. This endpoint exposes the same privacy trail that every
    memory op / approval decision / dropped candidate writes to, so the
    corrections are finally readable — satisfying the C3 \"corrections are
    wired, not just written\" acceptance criterion.

    ``drop`` events (GOV-1.6 / C5) are dropped extraction candidates:
    ``claim_id`` is ``None`` and the candidate shape (claim_type / scope /
    confidence) lives in ``details``. Filter with ``?event_type=drop`` to
    see only calibration drops.

    Always scoped to ``(user_id, workspace_id)`` (the workspace isolation
    guardrail). A bad ``event_type`` surfaces as a 422 (raised by the
    service).

    Args:
        event_type (None | str | Unset):
        page (int | Unset):  Default: 1.
        per_page (int | Unset):  Default: 50.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ListCorrectionsApiV2PersonalMemoryCorrectionsGetResponseListCorrectionsApiV2PersonalMemoryCorrectionsGet
    """

    return (
        await asyncio_detailed(
            client=client,
            event_type=event_type,
            page=page,
            per_page=per_page,
        )
    ).parsed
