from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    model_name: None | str | Unset = UNSET,
    dataset_id: None | str | Unset = UNSET,
    threshold: float | Unset = 0.5,
    limit: int | Unset = 10,
    accept_version: str | Unset = "v1",
) -> dict[str, Any]:
    headers: dict[str, Any] = {}
    if not isinstance(accept_version, Unset):
        headers["Accept-Version"] = accept_version

    params: dict[str, Any] = {}

    json_model_name: None | str | Unset
    if isinstance(model_name, Unset):
        json_model_name = UNSET
    else:
        json_model_name = model_name
    params["model_name"] = json_model_name

    json_dataset_id: None | str | Unset
    if isinstance(dataset_id, Unset):
        json_dataset_id = UNSET
    else:
        json_dataset_id = dataset_id
    params["dataset_id"] = json_dataset_id

    params["threshold"] = threshold

    params["limit"] = limit

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/api/evaluation/regressions",
        "params": params,
    }

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
    *,
    client: AuthenticatedClient | Client,
    model_name: None | str | Unset = UNSET,
    dataset_id: None | str | Unset = UNSET,
    threshold: float | Unset = 0.5,
    limit: int | Unset = 10,
    accept_version: str | Unset = "v1",
) -> Response[Any | HTTPValidationError]:
    """Detect Regressions

     Detect quality regressions by comparing recent eval runs for the same model+dataset.

    Args:
        model_name (None | str | Unset):
        dataset_id (None | str | Unset):
        threshold (float | Unset):  Default: 0.5.
        limit (int | Unset):  Default: 10.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        model_name=model_name,
        dataset_id=dataset_id,
        threshold=threshold,
        limit=limit,
        accept_version=accept_version,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    model_name: None | str | Unset = UNSET,
    dataset_id: None | str | Unset = UNSET,
    threshold: float | Unset = 0.5,
    limit: int | Unset = 10,
    accept_version: str | Unset = "v1",
) -> Any | HTTPValidationError | None:
    """Detect Regressions

     Detect quality regressions by comparing recent eval runs for the same model+dataset.

    Args:
        model_name (None | str | Unset):
        dataset_id (None | str | Unset):
        threshold (float | Unset):  Default: 0.5.
        limit (int | Unset):  Default: 10.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return sync_detailed(
        client=client,
        model_name=model_name,
        dataset_id=dataset_id,
        threshold=threshold,
        limit=limit,
        accept_version=accept_version,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    model_name: None | str | Unset = UNSET,
    dataset_id: None | str | Unset = UNSET,
    threshold: float | Unset = 0.5,
    limit: int | Unset = 10,
    accept_version: str | Unset = "v1",
) -> Response[Any | HTTPValidationError]:
    """Detect Regressions

     Detect quality regressions by comparing recent eval runs for the same model+dataset.

    Args:
        model_name (None | str | Unset):
        dataset_id (None | str | Unset):
        threshold (float | Unset):  Default: 0.5.
        limit (int | Unset):  Default: 10.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Any | HTTPValidationError]
    """

    kwargs = _get_kwargs(
        model_name=model_name,
        dataset_id=dataset_id,
        threshold=threshold,
        limit=limit,
        accept_version=accept_version,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    model_name: None | str | Unset = UNSET,
    dataset_id: None | str | Unset = UNSET,
    threshold: float | Unset = 0.5,
    limit: int | Unset = 10,
    accept_version: str | Unset = "v1",
) -> Any | HTTPValidationError | None:
    """Detect Regressions

     Detect quality regressions by comparing recent eval runs for the same model+dataset.

    Args:
        model_name (None | str | Unset):
        dataset_id (None | str | Unset):
        threshold (float | Unset):  Default: 0.5.
        limit (int | Unset):  Default: 10.
        accept_version (str | Unset):  Default: 'v1'.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Any | HTTPValidationError
    """

    return (
        await asyncio_detailed(
            client=client,
            model_name=model_name,
            dataset_id=dataset_id,
            threshold=threshold,
            limit=limit,
            accept_version=accept_version,
        )
    ).parsed
