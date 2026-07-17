from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.playground_action_request import PlaygroundActionRequest
from ...types import UNSET, Response, Unset


def _get_kwargs(
    slug: str,
    action: str,
    *,
    body: None | PlaygroundActionRequest | Unset = UNSET,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/integrations/{slug}/playground/{action}".format(
            slug=quote(str(slug), safe=""),
            action=quote(str(action), safe=""),
        ),
    }

    if isinstance(body, PlaygroundActionRequest):
        _kwargs["json"] = body.to_dict()
    else:
        _kwargs["json"] = body

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
    slug: str,
    action: str,
    *,
    client: AuthenticatedClient,
    body: None | PlaygroundActionRequest | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Playground Action

     Execute a demo action using Flowmanner's sandbox credentials.

    Rate-limited to 5 requests/minute per user per integration.
    Returns the real or mock API response for display.
    Gated by the ``integration_playground_v1`` feature flag.

    Args:
        slug (str):
        action (str):
        body (None | PlaygroundActionRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        slug=slug,
        action=action,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    slug: str,
    action: str,
    *,
    client: AuthenticatedClient,
    body: None | PlaygroundActionRequest | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Playground Action

     Execute a demo action using Flowmanner's sandbox credentials.

    Rate-limited to 5 requests/minute per user per integration.
    Returns the real or mock API response for display.
    Gated by the ``integration_playground_v1`` feature flag.

    Args:
        slug (str):
        action (str):
        body (None | PlaygroundActionRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        slug=slug,
        action=action,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    slug: str,
    action: str,
    *,
    client: AuthenticatedClient,
    body: None | PlaygroundActionRequest | Unset = UNSET,
) -> Response[Any | HTTPValidationError]:
    """Playground Action

     Execute a demo action using Flowmanner's sandbox credentials.

    Rate-limited to 5 requests/minute per user per integration.
    Returns the real or mock API response for display.
    Gated by the ``integration_playground_v1`` feature flag.

    Args:
        slug (str):
        action (str):
        body (None | PlaygroundActionRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        slug=slug,
        action=action,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    slug: str,
    action: str,
    *,
    client: AuthenticatedClient,
    body: None | PlaygroundActionRequest | Unset = UNSET,
) -> Any | HTTPValidationError | None:
    """Playground Action

     Execute a demo action using Flowmanner's sandbox credentials.

    Rate-limited to 5 requests/minute per user per integration.
    Returns the real or mock API response for display.
    Gated by the ``integration_playground_v1`` feature flag.

    Args:
        slug (str):
        action (str):
        body (None | PlaygroundActionRequest | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            slug=slug,
            action=action,
            client=client,
            body=body,
        )
    ).parsed
