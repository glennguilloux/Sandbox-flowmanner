from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.feedback_pattern_response import FeedbackPatternResponse
from ...models.feedback_pattern_update import FeedbackPatternUpdate
from ...models.http_validation_error import HTTPValidationError
from ...types import Response, Unset


def _get_kwargs(
    pattern_id: str,
    *,
    body: FeedbackPatternUpdate,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "patch",
        "url": "/api/feedback/patterns/{pattern_id}".format(
            pattern_id=quote(str(pattern_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> FeedbackPatternResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = FeedbackPatternResponse.from_dict(response.json())

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
) -> Response[FeedbackPatternResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    pattern_id: str,
    *,
    client: AuthenticatedClient,
    body: FeedbackPatternUpdate,
    accept_version: str | Unset = "v1",
) -> Response[FeedbackPatternResponse | HTTPValidationError]:
    """Update Pattern Endpoint

     Update a feedback pattern (status, suggested_fix).

    Args:
        pattern_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (FeedbackPatternUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeedbackPatternResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        pattern_id=pattern_id,
        body=body,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    pattern_id: str,
    *,
    client: AuthenticatedClient,
    body: FeedbackPatternUpdate,
    accept_version: str | Unset = "v1",
) -> FeedbackPatternResponse | HTTPValidationError | None:
    """Update Pattern Endpoint

     Update a feedback pattern (status, suggested_fix).

    Args:
        pattern_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (FeedbackPatternUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeedbackPatternResponse | HTTPValidationError
    """

    return sync_detailed(
        pattern_id=pattern_id,
        client=client,
        body=body,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    pattern_id: str,
    *,
    client: AuthenticatedClient,
    body: FeedbackPatternUpdate,
    accept_version: str | Unset = "v1",
) -> Response[FeedbackPatternResponse | HTTPValidationError]:
    """Update Pattern Endpoint

     Update a feedback pattern (status, suggested_fix).

    Args:
        pattern_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (FeedbackPatternUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeedbackPatternResponse | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        pattern_id=pattern_id,
        body=body,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    pattern_id: str,
    *,
    client: AuthenticatedClient,
    body: FeedbackPatternUpdate,
    accept_version: str | Unset = "v1",
) -> FeedbackPatternResponse | HTTPValidationError | None:
    """Update Pattern Endpoint

     Update a feedback pattern (status, suggested_fix).

    Args:
        pattern_id (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (FeedbackPatternUpdate):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeedbackPatternResponse | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            pattern_id=pattern_id,
            client=client,
            body=body,
            accept_version=accept_version,
        )
    ).parsed
