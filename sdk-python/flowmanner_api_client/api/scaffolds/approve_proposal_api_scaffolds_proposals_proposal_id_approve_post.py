from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.approve_proposal_api_scaffolds_proposals_proposal_id_approve_post_response_approve_proposal_api_scaffolds_proposals_proposal_id_approve_post import (
    ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost,
)
from ...models.approve_request import ApproveRequest
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    proposal_id: UUID,
    *,
    body: ApproveRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/scaffolds/proposals/{proposal_id}/approve".format(
            proposal_id=quote(str(proposal_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost.from_dict(
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
    ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost
    | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    proposal_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ApproveRequest,
) -> Response[
    ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost
    | HTTPValidationError
]:
    """Approve Proposal

     Approve a scaffold proposal and apply it as the active version.

    Creates a new ScaffoldVersion with is_active=True, deactivates
    the previous active version, and updates the proposal status.

    Args:
        proposal_id (UUID):
        body (ApproveRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        proposal_id=proposal_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    proposal_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ApproveRequest,
) -> (
    ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost
    | HTTPValidationError
    | None
):
    """Approve Proposal

     Approve a scaffold proposal and apply it as the active version.

    Creates a new ScaffoldVersion with is_active=True, deactivates
    the previous active version, and updates the proposal status.

    Args:
        proposal_id (UUID):
        body (ApproveRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost | HTTPValidationError
    """

    return sync_detailed(
        proposal_id=proposal_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    proposal_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ApproveRequest,
) -> Response[
    ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost
    | HTTPValidationError
]:
    """Approve Proposal

     Approve a scaffold proposal and apply it as the active version.

    Creates a new ScaffoldVersion with is_active=True, deactivates
    the previous active version, and updates the proposal status.

    Args:
        proposal_id (UUID):
        body (ApproveRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        proposal_id=proposal_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    proposal_id: UUID,
    *,
    client: AuthenticatedClient,
    body: ApproveRequest,
) -> (
    ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost
    | HTTPValidationError
    | None
):
    """Approve Proposal

     Approve a scaffold proposal and apply it as the active version.

    Creates a new ScaffoldVersion with is_active=True, deactivates
    the previous active version, and updates the proposal status.

    Args:
        proposal_id (UUID):
        body (ApproveRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ApproveProposalApiScaffoldsProposalsProposalIdApprovePostResponseApproveProposalApiScaffoldsProposalsProposalIdApprovePost | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            proposal_id=proposal_id,
            client=client,
            body=body,
        )
    ).parsed
