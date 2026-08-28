"""Typed asynchronous client for accessing the NZ Vehicle Data Pipeline API."""

from urllib.parse import quote

import httpx2
from pydantic import ValidationError

from vehicle_mcp_server.config import ServerConfig
from vehicle_mcp_server.models import VehicleRevisionResponse


class PipelineError(Exception):
    """Base exception for pipeline client communication errors."""


class VehicleNotFoundError(PipelineError):
    """Raised when the requested vehicle does not exist in the pipeline (HTTP 404)."""


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

    def __init__(self, config: ServerConfig, http_client: httpx2.AsyncClient) -> None:
        self._config = config
        self._http_client = http_client
        self._base_url = str(config.pipeline_base_url).rstrip("/")

    async def get_current_vehicle(self, vin: str) -> VehicleRevisionResponse:
        """Retrieve the canonical record and audit metadata for one validated VIN."""
        encoded_vin = quote(vin, safe="")
        url = f"{self._base_url}/v1/vehicles/{encoded_vin}"

        try:
            response = await self._http_client.get(
                url,
                timeout=httpx2.Timeout(
                    connect=self._config.connect_timeout,
                    read=self._config.read_timeout,
                    write=self._config.write_timeout,
                    pool=self._config.pool_timeout,
                ),
            )
        except httpx2.TimeoutException as exc:
            raise PipelineTimeoutError(f"Request to pipeline timed out: {url}") from exc
        except (httpx2.NetworkError, httpx2.RemoteProtocolError) as exc:
            raise PipelineUnavailableError(
                f"Failed to connect to pipeline service at {url}"
            ) from exc

        if response.status_code == 200:
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

        if response.status_code in (502, 503, 504):
            raise PipelineUnavailableError(
                f"Pipeline returned service unavailable: {response.status_code}"
            )

        raise PipelineContractError(
            f"Unexpected pipeline HTTP status {response.status_code} from {url}"
        )
