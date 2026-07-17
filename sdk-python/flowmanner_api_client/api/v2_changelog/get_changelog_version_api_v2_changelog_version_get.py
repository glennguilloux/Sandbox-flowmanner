from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.get_changelog_version_api_v2_changelog_version_get_response_get_changelog_version_api_v2_changelog_version_get import (
    GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet,
)
from ...models.http_validation_error import HTTPValidationError
from ...types import Response


def _get_kwargs(
    version: str,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/v2/changelog/{version}".format(
            version=quote(str(version), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet
    | HTTPValidationError
    | None
):
    if response.status_code == 200:
        response_200 = (
            GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet.from_dict(
                response.json()
            )
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
    GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet | HTTPValidationError
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    version: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet | HTTPValidationError
]:
    """Get Changelog Version

     Fetch a single changelog entry by its version label (public). 404 if absent.

    Args:
        version (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        version=version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    version: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet
    | HTTPValidationError
    | None
):
    """Get Changelog Version

     Fetch a single changelog entry by its version label (public). 404 if absent.

    Args:
        version (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet | HTTPValidationError
    """

    return sync_detailed(
        version=version,
        client=client,
    ).parsed


async def asyncio_detailed(
    version: str,
    *,
    client: AuthenticatedClient | Client,
) -> Response[
    GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet | HTTPValidationError
]:
    """Get Changelog Version

     Fetch a single changelog entry by its version label (public). 404 if absent.

    Args:
        version (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        version=version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    version: str,
    *,
    client: AuthenticatedClient | Client,
) -> (
    GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet
    | HTTPValidationError
    | None
):
    """Get Changelog Version

     Fetch a single changelog entry by its version label (public). 404 if absent.

    Args:
        version (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        GetChangelogVersionApiV2ChangelogVersionGetResponseGetChangelogVersionApiV2ChangelogVersionGet | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            version=version,
            client=client,
        )
    ).parsed
