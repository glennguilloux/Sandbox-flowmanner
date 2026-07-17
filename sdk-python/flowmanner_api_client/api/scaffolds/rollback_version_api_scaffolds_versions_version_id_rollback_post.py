from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.rollback_version_api_scaffolds_versions_version_id_rollback_post_response_rollback_version_api_scaffolds_versions_version_id_rollback_post import (
    RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost,
)
from ...types import Response


def _get_kwargs(
    version_id: UUID,
) -> dict[str, Any]:
    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/scaffolds/versions/{version_id}/rollback".format(
            version_id=quote(str(version_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost
    | None
):
    if response.status_code == 200:
        response_200 = RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost.from_dict(
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
    | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[
    HTTPValidationError
    | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost
]:
    """Rollback Version

     Rollback to a specific scaffold version.

    Deactivates the current active version for this agent and
    activates the specified version.

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost]
    """

    kwargs = _get_kwargs(
        version_id=version_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> (
    HTTPValidationError
    | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost
    | None
):
    """Rollback Version

     Rollback to a specific scaffold version.

    Deactivates the current active version for this agent and
    activates the specified version.

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost
    """

    return sync_detailed(
        version_id=version_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> Response[
    HTTPValidationError
    | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost
]:
    """Rollback Version

     Rollback to a specific scaffold version.

    Deactivates the current active version for this agent and
    activates the specified version.

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost]
    """

    kwargs = _get_kwargs(
        version_id=version_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    version_id: UUID,
    *,
    client: AuthenticatedClient,
) -> (
    HTTPValidationError
    | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost
    | None
):
    """Rollback Version

     Rollback to a specific scaffold version.

    Deactivates the current active version for this agent and
    activates the specified version.

    Args:
        version_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | RollbackVersionApiScaffoldsVersionsVersionIdRollbackPostResponseRollbackVersionApiScaffoldsVersionsVersionIdRollbackPost
    """

    return (
        await asyncio_detailed(
            version_id=version_id,
            client=client,
        )
    ).parsed
