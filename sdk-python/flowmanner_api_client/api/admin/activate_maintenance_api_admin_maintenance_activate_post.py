from http import HTTPStatus
from typing import Any, cast
from urllib.parse import quote

import httpx

from ...client import AuthenticatedClient, Client
from ...types import Response, UNSET
from ... import errors

from ...models.activate_maintenance_api_admin_maintenance_activate_post_data import (
    ActivateMaintenanceApiAdminMaintenanceActivatePostData,
)
from ...models.http_validation_error import HTTPValidationError
from ...models.maintenance_status import MaintenanceStatus
from typing import cast


def _get_kwargs(
    *,
    body: ActivateMaintenanceApiAdminMaintenanceActivatePostData,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/admin/maintenance/activate",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MaintenanceStatus | None:
    if response.status_code == 200:
        response_200 = MaintenanceStatus.from_dict(response.json())

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
) -> Response[HTTPValidationError | MaintenanceStatus]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    body: ActivateMaintenanceApiAdminMaintenanceActivatePostData,
) -> Response[HTTPValidationError | MaintenanceStatus]:
    """Activate Maintenance

    Args:
        body (ActivateMaintenanceApiAdminMaintenanceActivatePostData):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MaintenanceStatus]
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
    body: ActivateMaintenanceApiAdminMaintenanceActivatePostData,
) -> HTTPValidationError | MaintenanceStatus | None:
    """Activate Maintenance

    Args:
        body (ActivateMaintenanceApiAdminMaintenanceActivatePostData):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MaintenanceStatus
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    body: ActivateMaintenanceApiAdminMaintenanceActivatePostData,
) -> Response[HTTPValidationError | MaintenanceStatus]:
    """Activate Maintenance

    Args:
        body (ActivateMaintenanceApiAdminMaintenanceActivatePostData):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MaintenanceStatus]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    body: ActivateMaintenanceApiAdminMaintenanceActivatePostData,
) -> HTTPValidationError | MaintenanceStatus | None:
    """Activate Maintenance

    Args:
        body (ActivateMaintenanceApiAdminMaintenanceActivatePostData):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MaintenanceStatus
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
