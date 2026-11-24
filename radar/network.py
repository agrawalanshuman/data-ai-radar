"""Bounded HTTP with explicit timeout and no redirects."""

from time import monotonic

import httpx


class NetworkFailure(Exception):
    pass


class RejectedResponse(NetworkFailure):
    pass


def read_response(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    limit: int,
    seconds: float,
    retries: int = 0,
    read_seconds: float = 3,
    **kwargs,
) -> bytes:
    deadline = monotonic() + seconds
    for attempt in range(retries + 1):
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        timeout = httpx.Timeout(min(remaining, 5), read=min(remaining, read_seconds))
        try:
            with client.stream(
                method, url, timeout=timeout, follow_redirects=False, **kwargs
            ) as response:
                if response.status_code in {401, 403}:
                    raise RejectedResponse(
                        "Access denied (check the selected provider credential or access)."
                    )
                if response.status_code == 429:
                    raise RejectedResponse("Rate limit or quota reached.")
                if response.status_code in {502, 503, 504} and attempt < retries:
                    continue
                if not response.is_success:
                    raise RejectedResponse(f"Request returned HTTP {response.status_code}.")
                output = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() > deadline or len(output) + len(chunk) > limit:
                        raise RejectedResponse("Response exceeded its time or size limit.")
                    output.extend(chunk)
                return bytes(output)
        except httpx.TransportError:
            if attempt == retries:
                break
    raise NetworkFailure("Request timed out or the service could not be reached.")
