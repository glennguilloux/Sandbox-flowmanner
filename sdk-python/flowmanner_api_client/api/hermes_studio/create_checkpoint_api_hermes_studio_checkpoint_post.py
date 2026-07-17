from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.checkpoint_request import CheckpointRequest
from ...models.create_checkpoint_api_hermes_studio_checkpoint_post_response_create_checkpoint_api_hermes_studio_checkpoint_post import (
    CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    *,
    body: CheckpointRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/hermes-studio/checkpoint",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost.from_dict(
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
    CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost
    | HTTPValidationError
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
    body: CheckpointRequest,
) -> Response[
    CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost
    | HTTPValidationError
]:
    """Create Checkpoint

     Compress a transcript into a handoff summary.

    ``summarize`` is NOT called inside the HTTP request — this endpoint is
    sync and deterministic. To actually produce the summary you call your LLM
    with the returned ``prompt`` and POST the summary back, OR wire a
    summarizer callable server-side. We return the prompt + message plan so
    the caller can run the model themselves (keeps this endpoint free of any
    provider secret in the request path and avoids blocking the request).

    Args:
        body (CheckpointRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost | HTTPValidationError]
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
    body: CheckpointRequest,
) -> (
    CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost
    | HTTPValidationError
    | None
):
    """Create Checkpoint

     Compress a transcript into a handoff summary.

    ``summarize`` is NOT called inside the HTTP request — this endpoint is
    sync and deterministic. To actually produce the summary you call your LLM
    with the returned ``prompt`` and POST the summary back, OR wire a
    summarizer callable server-side. We return the prompt + message plan so
    the caller can run the model themselves (keeps this endpoint free of any
    provider secret in the request path and avoids blocking the request).

    Args:
        body (CheckpointRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: CheckpointRequest,
) -> Response[
    CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost
    | HTTPValidationError
]:
    """Create Checkpoint

     Compress a transcript into a handoff summary.

    ``summarize`` is NOT called inside the HTTP request — this endpoint is
    sync and deterministic. To actually produce the summary you call your LLM
    with the returned ``prompt`` and POST the summary back, OR wire a
    summarizer callable server-side. We return the prompt + message plan so
    the caller can run the model themselves (keeps this endpoint free of any
    provider secret in the request path and avoids blocking the request).

    Args:
        body (CheckpointRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: CheckpointRequest,
) -> (
    CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost
    | HTTPValidationError
    | None
):
    """Create Checkpoint

     Compress a transcript into a handoff summary.

    ``summarize`` is NOT called inside the HTTP request — this endpoint is
    sync and deterministic. To actually produce the summary you call your LLM
    with the returned ``prompt`` and POST the summary back, OR wire a
    summarizer callable server-side. We return the prompt + message plan so
    the caller can run the model themselves (keeps this endpoint free of any
    provider secret in the request path and avoids blocking the request).

    Args:
        body (CheckpointRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        CreateCheckpointApiHermesStudioCheckpointPostResponseCreateCheckpointApiHermesStudioCheckpointPost | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
