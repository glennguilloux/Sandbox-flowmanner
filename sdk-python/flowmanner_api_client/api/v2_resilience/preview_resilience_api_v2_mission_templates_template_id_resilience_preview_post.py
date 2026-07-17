from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.preview_resilience_api_v2_mission_templates_template_id_resilience_preview_post_body_8 import (
    PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8,
)
from ...models.preview_resilience_api_v2_mission_templates_template_id_resilience_preview_post_response_preview_resilience_api_v2_mission_templates_template_id_resilience_preview_post import (
    PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost,
)
from ...types import Response


def _get_kwargs(
    template_id: str,
    *,
    body: PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/v2/mission-templates/{template_id}/resilience/preview".format(
            template_id=quote(str(template_id), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> (
    HTTPValidationError
    | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost
    | None
):
    if response.status_code == 200:
        response_200 = PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost.from_dict(
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
    | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost
]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    template_id: str,
    *,
    client: AuthenticatedClient,
    body: PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8,
) -> Response[
    HTTPValidationError
    | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost
]:
    """Preview Resilience

     Return the wrapped plan without persisting a variant.

    Args:
        template_id (str):
        body (PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost]
    """

    kwargs = _get_kwargs(
        template_id=template_id,
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    template_id: str,
    *,
    client: AuthenticatedClient,
    body: PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8,
) -> (
    HTTPValidationError
    | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost
    | None
):
    """Preview Resilience

     Return the wrapped plan without persisting a variant.

    Args:
        template_id (str):
        body (PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost
    """

    return sync_detailed(
        template_id=template_id,
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    template_id: str,
    *,
    client: AuthenticatedClient,
    body: PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8,
) -> Response[
    HTTPValidationError
    | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost
]:
    """Preview Resilience

     Return the wrapped plan without persisting a variant.

    Args:
        template_id (str):
        body (PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost]
    """

    kwargs = _get_kwargs(
        template_id=template_id,
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    template_id: str,
    *,
    client: AuthenticatedClient,
    body: PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8,
) -> (
    HTTPValidationError
    | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost
    | None
):
    """Preview Resilience

     Return the wrapped plan without persisting a variant.

    Args:
        template_id (str):
        body (PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostBody8):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | PreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPostResponsePreviewResilienceApiV2MissionTemplatesTemplateIdResiliencePreviewPost
    """

    return (
        await asyncio_detailed(
            template_id=template_id,
            client=client,
            body=body,
        )
    ).parsed
