from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.prompt_version_response import PromptVersionResponse
from ...types import Response


def _get_kwargs(
    prompt_id: int,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/prompts/{prompt_id}".format(
            prompt_id=quote(str(prompt_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | PromptVersionResponse | None:
    if response.status_code == 200:
        response_200 = PromptVersionResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | PromptVersionResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    prompt_id: int,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | PromptVersionResponse]:
    """Get Prompt

     Get a specific prompt version by ID.

    Args:
        prompt_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PromptVersionResponse]
    """

    kwargs = _get_kwargs(
        prompt_id=prompt_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    prompt_id: int,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | PromptVersionResponse | None:
    """Get Prompt

     Get a specific prompt version by ID.

    Args:
        prompt_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PromptVersionResponse
    """

    return sync_detailed(
        prompt_id=prompt_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    prompt_id: int,
    *,
    client: AuthenticatedClient,
) -> Response[HTTPValidationError | PromptVersionResponse]:
    """Get Prompt

     Get a specific prompt version by ID.

    Args:
        prompt_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PromptVersionResponse]
    """

    kwargs = _get_kwargs(
        prompt_id=prompt_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    prompt_id: int,
    *,
    client: AuthenticatedClient,
) -> HTTPValidationError | PromptVersionResponse | None:
    """Get Prompt

     Get a specific prompt version by ID.

    Args:
        prompt_id (int):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PromptVersionResponse
    """

    return (
        await asyncio_detailed(
            prompt_id=prompt_id,
            client=client,
        )
    ).parsed
