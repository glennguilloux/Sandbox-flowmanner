from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.approval_decision import ApprovalDecision
from ...models.http_validation_error import HTTPValidationError
from ...models.resolve_agent_approval_api_governance_agents_session_id_approval_post_response_resolve_agent_approval_api_governance_agents_session_id_approval_post import (
    ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost,
)
from ...types import Response


def _get_kwargs(
    session_id: str,
    *,
    body: ApprovalDecision,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/governance/agents/{session_id}/approval".format(
            session_id=quote(str(session_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost
    | None
):
    if response.status_code == 200:
        response_200 = ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost.from_dict(
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
    | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient,
    body: ApprovalDecision,
) -> Response[
    HTTPValidationError
    | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost
]:
    r"""Resolve a ControlFlowAgent approval request

     Record a human approval/rejection for a paused ControlFlowAgent session.

    Body: {\"decision\": \"approved\"|\"rejected\", \"tool_index\"?: int}

    Authz (G-4): FAILS CLOSED. An approval decision is a sensitive, state-changing
    action, so it is restricted to the session owner or an admin (mirrors the HITL
    inbox path in app/api/v1/hitl.py, which rejects decisions from non-owners with
    404). If the caller is not the owner and not an admin, the request is denied
    with 403 — never fail-open. The agent's ``resolve_approval`` also enforces
    ownership as defense-in-depth (raises ValueError -> 400).

    WARNING: this endpoint is NOT the live approval gate (the HITL inbox is). It
    has no production caller. Treat a green test here as proof of the *authz guard
    only*, not of an end-to-end approval flow.

    Args:
        session_id (str):
        body (ApprovalDecision):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    session_id: str,
    *,
    client: AuthenticatedClient,
    body: ApprovalDecision,
) -> (
    HTTPValidationError
    | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost
    | None
):
    r"""Resolve a ControlFlowAgent approval request

     Record a human approval/rejection for a paused ControlFlowAgent session.

    Body: {\"decision\": \"approved\"|\"rejected\", \"tool_index\"?: int}

    Authz (G-4): FAILS CLOSED. An approval decision is a sensitive, state-changing
    action, so it is restricted to the session owner or an admin (mirrors the HITL
    inbox path in app/api/v1/hitl.py, which rejects decisions from non-owners with
    404). If the caller is not the owner and not an admin, the request is denied
    with 403 — never fail-open. The agent's ``resolve_approval`` also enforces
    ownership as defense-in-depth (raises ValueError -> 400).

    WARNING: this endpoint is NOT the live approval gate (the HITL inbox is). It
    has no production caller. Treat a green test here as proof of the *authz guard
    only*, not of an end-to-end approval flow.

    Args:
        session_id (str):
        body (ApprovalDecision):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost
    """

    return sync_detailed(
        session_id=session_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    session_id: str,
    *,
    client: AuthenticatedClient,
    body: ApprovalDecision,
) -> Response[
    HTTPValidationError
    | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost
]:
    r"""Resolve a ControlFlowAgent approval request

     Record a human approval/rejection for a paused ControlFlowAgent session.

    Body: {\"decision\": \"approved\"|\"rejected\", \"tool_index\"?: int}

    Authz (G-4): FAILS CLOSED. An approval decision is a sensitive, state-changing
    action, so it is restricted to the session owner or an admin (mirrors the HITL
    inbox path in app/api/v1/hitl.py, which rejects decisions from non-owners with
    404). If the caller is not the owner and not an admin, the request is denied
    with 403 — never fail-open. The agent's ``resolve_approval`` also enforces
    ownership as defense-in-depth (raises ValueError -> 400).

    WARNING: this endpoint is NOT the live approval gate (the HITL inbox is). It
    has no production caller. Treat a green test here as proof of the *authz guard
    only*, not of an end-to-end approval flow.

    Args:
        session_id (str):
        body (ApprovalDecision):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost]
    """

    kwargs = _get_kwargs(
        session_id=session_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    session_id: str,
    *,
    client: AuthenticatedClient,
    body: ApprovalDecision,
) -> (
    HTTPValidationError
    | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost
    | None
):
    r"""Resolve a ControlFlowAgent approval request

     Record a human approval/rejection for a paused ControlFlowAgent session.

    Body: {\"decision\": \"approved\"|\"rejected\", \"tool_index\"?: int}

    Authz (G-4): FAILS CLOSED. An approval decision is a sensitive, state-changing
    action, so it is restricted to the session owner or an admin (mirrors the HITL
    inbox path in app/api/v1/hitl.py, which rejects decisions from non-owners with
    404). If the caller is not the owner and not an admin, the request is denied
    with 403 — never fail-open. The agent's ``resolve_approval`` also enforces
    ownership as defense-in-depth (raises ValueError -> 400).

    WARNING: this endpoint is NOT the live approval gate (the HITL inbox is). It
    has no production caller. Treat a green test here as proof of the *authz guard
    only*, not of an end-to-end approval flow.

    Args:
        session_id (str):
        body (ApprovalDecision):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | ResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPostResponseResolveAgentApprovalApiGovernanceAgentsSessionIdApprovalPost
    """

    return (
        await asyncio_detailed(
            session_id=session_id,
            client=client,
            body=body,
        )
    ).parsed
