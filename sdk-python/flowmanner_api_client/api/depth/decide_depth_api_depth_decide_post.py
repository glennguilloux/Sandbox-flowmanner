from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.depth_decide_request import DepthDecideRequest
from ...models.depth_decision_response import DepthDecisionResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: DepthDecideRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/depth/decide",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DepthDecisionResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DepthDecisionResponse.from_dict(response.json())

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
) -> Response[DepthDecisionResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: DepthDecideRequest,
) -> Response[DepthDecisionResponse | HTTPValidationError]:
    """Decide Depth

     Compute a depth decision for the given inputs.

    This is an admin/testing endpoint that exposes the depth policy
    directly.  In production, the policy is called by MissionExecutor.

    Args:
        body (DepthDecideRequest): Request body for the depth decision endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DepthDecisionResponse | HTTPValidationError]
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
    client: AuthenticatedClient | Client,
    body: DepthDecideRequest,
) -> DepthDecisionResponse | HTTPValidationError | None:
    """Decide Depth

     Compute a depth decision for the given inputs.

    This is an admin/testing endpoint that exposes the depth policy
    directly.  In production, the policy is called by MissionExecutor.

    Args:
        body (DepthDecideRequest): Request body for the depth decision endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DepthDecisionResponse | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: DepthDecideRequest,
) -> Response[DepthDecisionResponse | HTTPValidationError]:
    """Decide Depth

     Compute a depth decision for the given inputs.

    This is an admin/testing endpoint that exposes the depth policy
    directly.  In production, the policy is called by MissionExecutor.

    Args:
        body (DepthDecideRequest): Request body for the depth decision endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DepthDecisionResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: DepthDecideRequest,
) -> DepthDecisionResponse | HTTPValidationError | None:
    """Decide Depth

     Compute a depth decision for the given inputs.

    This is an admin/testing endpoint that exposes the depth policy
    directly.  In production, the policy is called by MissionExecutor.

    Args:
        body (DepthDecideRequest): Request body for the depth decision endpoint.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DepthDecisionResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
