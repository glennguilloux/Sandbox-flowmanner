from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.marketplace_review import MarketplaceReview
from ...models.submit_review_api_marketplace_listings_slug_reviews_post_data import (
    SubmitReviewApiMarketplaceListingsSlugReviewsPostData,
)
from ...types import Response, Unset


def _get_kwargs(
    slug: str,
    *,
    body: SubmitReviewApiMarketplaceListingsSlugReviewsPostData,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/api/marketplace/listings/{slug}/reviews".format(
            slug=quote(str(slug), safe=""),
        ),
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | MarketplaceReview | None:
    if response.status_code == 200:
        response_200 = MarketplaceReview.from_dict(response.json())

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
) -> Response[HTTPValidationError | MarketplaceReview]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    slug: str,
    *,
    client: AuthenticatedClient,
    body: SubmitReviewApiMarketplaceListingsSlugReviewsPostData,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | MarketplaceReview]:
    """Submit Review

    Args:
        slug (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (SubmitReviewApiMarketplaceListingsSlugReviewsPostData):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MarketplaceReview]
    """

    kwargs = _get_kwargs(
        slug=slug,
        body=body,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    slug: str,
    *,
    client: AuthenticatedClient,
    body: SubmitReviewApiMarketplaceListingsSlugReviewsPostData,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | MarketplaceReview | None:
    """Submit Review

    Args:
        slug (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (SubmitReviewApiMarketplaceListingsSlugReviewsPostData):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MarketplaceReview
    """

    return sync_detailed(
        slug=slug,
        client=client,
        body=body,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    slug: str,
    *,
    client: AuthenticatedClient,
    body: SubmitReviewApiMarketplaceListingsSlugReviewsPostData,
    accept_version: str | Unset = "v1",
) -> Response[HTTPValidationError | MarketplaceReview]:
    """Submit Review

    Args:
        slug (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (SubmitReviewApiMarketplaceListingsSlugReviewsPostData):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | MarketplaceReview]
    """

    kwargs = _get_kwargs(
        slug=slug,
        body=body,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    slug: str,
    *,
    client: AuthenticatedClient,
    body: SubmitReviewApiMarketplaceListingsSlugReviewsPostData,
    accept_version: str | Unset = "v1",
) -> HTTPValidationError | MarketplaceReview | None:
    """Submit Review

    Args:
        slug (str):
        accept_version (str | Unset):  Default: 'v1'.
        body (SubmitReviewApiMarketplaceListingsSlugReviewsPostData):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | MarketplaceReview
    """

    return (
        await asyncio_detailed(
            slug=slug,
            client=client,
            body=body,
            accept_version=accept_version,
        )
    ).parsed
