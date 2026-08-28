import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from urllib.parse import quote

import httpx2
from pydantic import ValidationError

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import SourceObservationResponse, VehicleRevisionResponse


class PipelineError(Exception):
    """Base exception for pipeline client communication errors."""


class VehicleNotFoundError(PipelineError):
    """Raised when the requested vehicle does not exist in the pipeline (HTTP 404)."""


class RevisionNotFoundError(PipelineError):
    """Raised when the requested vehicle revision does not exist in the pipeline (HTTP 404)."""


class ObservationNotFoundError(PipelineError):
    """Raised when the requested source observation does not exist in the pipeline (HTTP 404)."""


class PipelineInvalidInputError(PipelineError):
    """Raised when the pipeline rejects input as unprocessable (HTTP 422)."""


class PipelineContractError(PipelineError):
    """Raised when the pipeline response violates the expected contract schema."""


class PipelineTimeoutError(PipelineError):
    """Raised when a request to the pipeline times out."""


class PipelineUnavailableError(PipelineError):
    """Raised when the pipeline service cannot be reached or returns a 5xx gateway error."""


class VehiclePipelineClient:
    """Async client performing typed, timed reads against the pipeline HTTP API."""

    def __init__(
        self,
        config: ServerConfig,
        http_client: httpx2.AsyncClient,
        sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._config = config
        self._http_client = http_client
        self._sleep = sleep_func
        self._base_url = str(config.pipeline_base_url).rstrip("/")

    def _check_response_size(self, response: httpx2.Response, url: str) -> None:
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > self._config.max_response_bytes:
            raise PipelineContractError(
                f"Pipeline response size header ({content_length} bytes) exceeds ceiling "
                f"of {self._config.max_response_bytes} bytes for {url}"
            )
        if len(response.content) > self._config.max_response_bytes:
            raise PipelineContractError(
                f"Pipeline response body ({len(response.content)} bytes) exceeds ceiling "
                f"of {self._config.max_response_bytes} bytes for {url}"
            )

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        params: dict[str, str] | None = None,
    ) -> httpx2.Response:
        delays = [0.2, 0.4]
        last_error: Exception | None = None

        for attempt in range(1, self._config.max_attempts + 1):
            try:
                response = await self._http_client.request(
                    method=method,
                    url=url,
                    params=params,
                    timeout=httpx2.Timeout(
                        connect=self._config.connect_timeout,
                        read=self._config.read_timeout,
                        write=self._config.write_timeout,
                        pool=self._config.pool_timeout,
                    ),
                )
            except asyncio.CancelledError:
                raise
            except httpx2.TimeoutException as exc:
                last_error = PipelineTimeoutError(f"Request to pipeline timed out: {url}")
                if attempt < self._config.max_attempts:
                    delay = delays[attempt - 1] if attempt - 1 < len(delays) else 0.4
                    await self._sleep(delay)
                    continue
                raise last_error from exc
            except (httpx2.NetworkError, httpx2.RemoteProtocolError) as exc:
                last_error = PipelineUnavailableError(
                    f"Failed to connect to pipeline service at {url}"
                )
                if attempt < self._config.max_attempts:
                    delay = delays[attempt - 1] if attempt - 1 < len(delays) else 0.4
                    await self._sleep(delay)
                    continue
                raise last_error from exc

            if response.status_code in (429, 502, 503, 504):
                last_error = PipelineUnavailableError(
                    f"Pipeline returned service unavailable status {response.status_code}"
                )
                if attempt < self._config.max_attempts:
                    retry_after = response.headers.get("retry-after")
                    delay = delays[attempt - 1] if attempt - 1 < len(delays) else 0.4
                    if retry_after:
                        try:
                            parsed = float(retry_after)
                            if 0 < parsed <= 2.0:
                                delay = parsed
                        except ValueError:
                            pass
                    await self._sleep(delay)
                    continue
                raise last_error

            return response

        if last_error:
            raise last_error
        raise PipelineUnavailableError("Max request attempts exhausted.")

    async def get_current_vehicle(self, vin: str) -> VehicleRevisionResponse:
        """Retrieve the canonical record and audit metadata for one validated VIN."""
        encoded_vin = quote(vin, safe="")
        url = f"{self._base_url}/v1/vehicles/{encoded_vin}"
        response = await self._request_with_retry("GET", url)

        if response.status_code == 200:
            self._check_response_size(response, url)
            try:
                data = response.json()
            except Exception as exc:
                raise PipelineContractError(
                    f"Pipeline response is not valid JSON from {url}"
                ) from exc

            try:
                return VehicleRevisionResponse.model_validate(data)
            except ValidationError as exc:
                raise PipelineContractError(
                    f"Pipeline response violates VehicleRevisionResponse contract: {exc}"
                ) from exc

        if response.status_code == 404:
            raise VehicleNotFoundError(f"Vehicle with VIN '{vin}' not found.")

        if response.status_code == 422:
            raise PipelineInvalidInputError(f"Pipeline rejected VIN '{vin}' as invalid input.")

        raise PipelineContractError(
            f"Unexpected pipeline HTTP status {response.status_code} from {url}"
        )

    async def get_vehicle_history(
        self,
        vin: str,
        limit: int = 20,
        before_revision: int | None = None,
    ) -> list[VehicleRevisionResponse]:
        """Retrieve historical revisions for a vehicle in newest-first order."""
        encoded_vin = quote(vin, safe="")
        url = f"{self._base_url}/v1/vehicles/{encoded_vin}/history"
        params: dict[str, str] = {"limit": str(limit)}
        if before_revision is not None:
            params["before_revision"] = str(before_revision)

        response = await self._request_with_retry("GET", url, params=params)

        if response.status_code == 200:
            self._check_response_size(response, url)
            try:
                data = response.json()
            except Exception as exc:
                raise PipelineContractError(
                    f"Pipeline response is not valid JSON from {url}"
                ) from exc

            if not isinstance(data, list):
                raise PipelineContractError(f"Expected list from {url}, got {type(data)}")

            if len(data) == 0 and before_revision is None:
                raise VehicleNotFoundError(f"Vehicle with VIN '{vin}' not found.")

            try:
                return [VehicleRevisionResponse.model_validate(item) for item in data]
            except ValidationError as exc:
                raise PipelineContractError(
                    f"Pipeline history item violates VehicleRevisionResponse contract: {exc}"
                ) from exc

        if response.status_code == 404:
            raise VehicleNotFoundError(f"Vehicle with VIN '{vin}' not found.")

        if response.status_code == 422:
            raise PipelineInvalidInputError(f"Pipeline rejected history query for VIN '{vin}'.")

        raise PipelineContractError(
            f"Unexpected pipeline HTTP status {response.status_code} from {url}"
        )

    async def get_vehicle_revision(
        self,
        vin: str,
        revision_number: int,
    ) -> VehicleRevisionResponse:
        """Retrieve one exact immutable canonical revision by number."""
        encoded_vin = quote(vin, safe="")
        url = f"{self._base_url}/v1/vehicles/{encoded_vin}/revisions/{revision_number}"
        response = await self._request_with_retry("GET", url)

        if response.status_code == 200:
            self._check_response_size(response, url)
            try:
                data = response.json()
            except Exception as exc:
                raise PipelineContractError(
                    f"Pipeline response is not valid JSON from {url}"
                ) from exc

            try:
                return VehicleRevisionResponse.model_validate(data)
            except ValidationError as exc:
                raise PipelineContractError(
                    f"Pipeline revision violates VehicleRevisionResponse contract: {exc}"
                ) from exc

        if response.status_code == 404:
            raise RevisionNotFoundError(
                f"Revision {revision_number} for vehicle with VIN '{vin}' not found."
            )

        if response.status_code == 422:
            raise PipelineInvalidInputError(
                f"Pipeline rejected revision request for VIN '{vin}' revision {revision_number}."
            )

        raise PipelineContractError(
            f"Unexpected pipeline HTTP status {response.status_code} from {url}"
        )

    async def get_source_observation(
        self,
        observation_id: str,
    ) -> SourceObservationResponse:
        """Retrieve one exact immutable source observation by ID."""
        encoded_id = quote(observation_id, safe="")
        url = f"{self._base_url}/v1/observations/{encoded_id}"
        response = await self._request_with_retry("GET", url)

        if response.status_code == 200:
            self._check_response_size(response, url)
            try:
                data = response.json()
            except Exception as exc:
                raise PipelineContractError(
                    f"Pipeline response is not valid JSON from {url}"
                ) from exc

            try:
                obs = SourceObservationResponse.model_validate(data)
            except ValidationError as exc:
                raise PipelineContractError(
                    f"Pipeline observation violates SourceObservationResponse contract: {exc}"
                ) from exc

            computed_hash = hashlib.sha256(obs.raw_payload.encode("utf-8")).hexdigest()
            expected_hash = obs.payload_hash_sha256.lower().removeprefix("sha256:")
            if computed_hash != expected_hash:
                raise PipelineContractError(
                    f"Payload SHA-256 mismatch for observation '{observation_id}': "
                    f"computed {computed_hash} != {expected_hash}"
                )

            return obs

        if response.status_code == 404:
            raise ObservationNotFoundError(f"Observation '{observation_id}' not found.")

        if response.status_code == 422:
            raise PipelineInvalidInputError(
                f"Pipeline rejected observation request for ID '{observation_id}'."
            )

        raise PipelineContractError(
            f"Unexpected pipeline HTTP status {response.status_code} from {url}"
        )
