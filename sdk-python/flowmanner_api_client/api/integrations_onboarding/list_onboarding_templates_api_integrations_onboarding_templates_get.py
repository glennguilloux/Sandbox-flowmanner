from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.template_list_response import TemplateListResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    integrations: None | str | Unset = UNSET,
) -> dict[str, Any]:
    params: dict[str, Any] = {}

    json_integrations: None | str | Unset
    if isinstance(integrations, Unset):
        json_integrations = UNSET
    else:
        json_integrations = integrations
    params["integrations"] = json_integrations

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/integrations/onboarding/templates",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | TemplateListResponse | None:
    if response.status_code == 200:
        response_200 = TemplateListResponse.from_dict(response.json())

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
) -> Response[HTTPValidationError | TemplateListResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient,
    integrations: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | TemplateListResponse]:
    r"""List Onboarding Templates

     List available integration onboarding template workflows.

    When ``integrations`` is provided, only templates whose required
    integrations are a subset of the connected set are returned.
    This powers the \"filtered by your tools\" step in the onboarding wizard.

    Args:
        integrations (None | str | Unset): Comma-separated list of connected integration slugs to
            filter by.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TemplateListResponse]
    """

    kwargs = _get_kwargs(
        integrations=integrations,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient,
    integrations: None | str | Unset = UNSET,
) -> HTTPValidationError | TemplateListResponse | None:
    r"""List Onboarding Templates

     List available integration onboarding template workflows.

    When ``integrations`` is provided, only templates whose required
    integrations are a subset of the connected set are returned.
    This powers the \"filtered by your tools\" step in the onboarding wizard.

    Args:
        integrations (None | str | Unset): Comma-separated list of connected integration slugs to
            filter by.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TemplateListResponse
    """

    return sync_detailed(
        client=client,
        integrations=integrations,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient,
    integrations: None | str | Unset = UNSET,
) -> Response[HTTPValidationError | TemplateListResponse]:
    r"""List Onboarding Templates

     List available integration onboarding template workflows.

    When ``integrations`` is provided, only templates whose required
    integrations are a subset of the connected set are returned.
    This powers the \"filtered by your tools\" step in the onboarding wizard.

    Args:
        integrations (None | str | Unset): Comma-separated list of connected integration slugs to
            filter by.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | TemplateListResponse]
    """

    kwargs = _get_kwargs(
        integrations=integrations,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient,
    integrations: None | str | Unset = UNSET,
) -> HTTPValidationError | TemplateListResponse | None:
    r"""List Onboarding Templates

     List available integration onboarding template workflows.

    When ``integrations`` is provided, only templates whose required
    integrations are a subset of the connected set are returned.
    This powers the \"filtered by your tools\" step in the onboarding wizard.

    Args:
        integrations (None | str | Unset): Comma-separated list of connected integration slugs to
            filter by.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | TemplateListResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            integrations=integrations,
        )
    ).parsed
