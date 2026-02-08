"""CapSolver API client for CAPTCHA solving.

Supports hCaptcha, reCaptcha v2/v3, Turnstile, image CAPTCHAs.

Issue #87: Alternative provider for hCaptcha when 2Captcha fails.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class CapSolverClient:
    """Async API client for the CapSolver CAPTCHA-solving service.

    Provides methods to solve various CAPTCHA types (hCaptcha, reCAPTCHA v2/v3,
    Cloudflare Turnstile, image CAPTCHAs) via the CapSolver REST API.

    Supports both context-manager and standalone usage patterns.  Tasks are
    created via ``createTask`` and polled for results via ``getTaskResult``.

    Attributes:
        BASE_URL: CapSolver API base URL.
        TASK_HCAPTCHA: Task type string for hCaptcha (proxyless).
        TASK_RECAPTCHA_V2: Task type string for reCAPTCHA v2 (proxyless).
        TASK_RECAPTCHA_V3: Task type string for reCAPTCHA v3 (proxyless).
        TASK_TURNSTILE: Task type string for Cloudflare Turnstile.
        TASK_IMAGE: Task type string for image-to-text recognition.

    Example::

        async with CapSolverClient(api_key) as solver:
            token = await solver.solve_hcaptcha(url, site_key)
    """

    BASE_URL = "https://api.capsolver.com"

    # Task types
    TASK_HCAPTCHA = "HCaptchaTaskProxyless"
    TASK_RECAPTCHA_V2 = "ReCaptchaV2TaskProxyless"
    TASK_RECAPTCHA_V3 = "ReCaptchaV3TaskProxyless"
    TASK_TURNSTILE = "AntiCloudflareTask"
    TASK_IMAGE = "ImageToTextTask"

    def __init__(
        self,
        api_key: str,
        polling_interval: float = 3.0,
        timeout: int = 180,
    ) -> None:
        """Initialise the CapSolver client.

        Args:
            api_key: CapSolver API key.
            polling_interval: Seconds between status checks (default 3).
            timeout: Maximum seconds to wait for a solution (default 180).
        """
        self.api_key = api_key
        self.polling_interval = polling_interval
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "CapSolverClient":
        """Async context manager entry -- create an aiohttp session."""
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """Async context manager exit -- close the aiohttp session."""
        if self.session:
            await self.session.close()

    async def _ensure_session(self) -> None:
        """Lazily create an aiohttp session if one does not already exist."""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def _create_task(self, task_data: Dict[str, Any]) -> str:
        """Create a CAPTCHA-solving task on the CapSolver API.

        Args:
            task_data: Task configuration dictionary (must include ``type``).

        Returns:
            The task ID assigned by CapSolver.

        Raises:
            Exception: If the API returns a non-zero ``errorId``.
        """
        await self._ensure_session()

        payload = {
            "clientKey": self.api_key,
            "task": task_data,
        }

        task_type = task_data.get("type")
        logger.debug("Creating CapSolver task: %s", task_type)

        url = f"{self.BASE_URL}/createTask"
        async with self.session.post(url, json=payload) as resp:
            data = await resp.json()

            if data.get("errorId") != 0:
                error_code = data.get("errorCode", "UNKNOWN")
                error_desc = data.get(
                    "errorDescription", "No description"
                )
                raise Exception(
                    f"CapSolver task creation failed: "
                    f"{error_code} - {error_desc}"
                )

            task_id = data.get("taskId")
            logger.info("CapSolver task created: %s", task_id)
            return task_id

    async def _get_task_result(
        self, task_id: str
    ) -> Dict[str, Any]:
        """Poll for task completion and return the solution.

        Args:
            task_id: Task ID obtained from :meth:`_create_task`.

        Returns:
            The ``solution`` dictionary from the CapSolver response.

        Raises:
            TimeoutError: If the solution is not ready within
                :attr:`timeout` seconds.
            Exception: If the task fails on the server side.
        """
        await self._ensure_session()

        payload = {
            "clientKey": self.api_key,
            "taskId": task_id,
        }

        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.timeout:
                raise TimeoutError(
                    f"CapSolver task {task_id} timed out "
                    f"after {self.timeout}s"
                )

            url = f"{self.BASE_URL}/getTaskResult"
            async with self.session.post(url, json=payload) as resp:
                data = await resp.json()

                if data.get("errorId") != 0:
                    error_code = data.get("errorCode", "UNKNOWN")
                    error_desc = data.get(
                        "errorDescription", "No description"
                    )
                    raise Exception(
                        f"CapSolver task failed: "
                        f"{error_code} - {error_desc}"
                    )

                status = data.get("status")

                if status == "ready":
                    solution = data.get("solution", {})
                    logger.info(
                        "CapSolver task %s solved in %.1fs",
                        task_id,
                        elapsed,
                    )
                    return solution

                if status == "failed":
                    raise Exception(
                        f"CapSolver task {task_id} failed"
                    )

                # Status is "processing", wait and retry
                logger.debug(
                    "CapSolver task %s still processing "
                    "(%.1fs elapsed)",
                    task_id,
                    elapsed,
                )
                await asyncio.sleep(self.polling_interval)

    async def solve_hcaptcha(
        self,
        site_url: str,
        site_key: str,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> str:
        """Solve an hCaptcha challenge.

        Args:
            site_url: URL of the page where the CAPTCHA appears.
            site_key: hCaptcha site key.
            user_agent: Browser user-agent string (optional).
            proxy: Proxy in ``user:pass@ip:port`` format (optional).

        Returns:
            The hCaptcha response token.
        """
        task_data: Dict[str, Any] = {
            "type": self.TASK_HCAPTCHA,
            "websiteURL": site_url,
            "websiteKey": site_key,
        }

        if user_agent:
            task_data["userAgent"] = user_agent

        if proxy:
            task_data["proxy"] = f"http://{proxy}"

        task_id = await self._create_task(task_data)
        solution = await self._get_task_result(task_id)

        return solution.get("gRecaptchaResponse", "")

    async def solve_recaptcha_v2(
        self,
        site_url: str,
        site_key: str,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
        invisible: bool = False,
    ) -> str:
        """Solve a reCAPTCHA v2 challenge.

        Args:
            site_url: URL of the page where the CAPTCHA appears.
            site_key: reCAPTCHA site key.
            user_agent: Browser user-agent string (optional).
            proxy: Proxy in ``user:pass@ip:port`` format (optional).
            invisible: Whether this is an invisible reCAPTCHA
                (default ``False``).

        Returns:
            The reCAPTCHA response token.
        """
        task_data: Dict[str, Any] = {
            "type": self.TASK_RECAPTCHA_V2,
            "websiteURL": site_url,
            "websiteKey": site_key,
        }

        if user_agent:
            task_data["userAgent"] = user_agent

        if proxy:
            task_data["proxy"] = f"http://{proxy}"

        if invisible:
            task_data["isInvisible"] = True

        task_id = await self._create_task(task_data)
        solution = await self._get_task_result(task_id)

        return solution.get("gRecaptchaResponse", "")

    async def solve_recaptcha_v3(
        self,
        site_url: str,
        site_key: str,
        action: str = "submit",
        min_score: float = 0.7,
    ) -> str:
        """Solve a reCAPTCHA v3 challenge.

        Args:
            site_url: URL of the page where the CAPTCHA appears.
            site_key: reCAPTCHA site key.
            action: reCAPTCHA action name (default ``"submit"``).
            min_score: Minimum acceptable score (default 0.7).

        Returns:
            The reCAPTCHA response token.
        """
        task_data: Dict[str, Any] = {
            "type": self.TASK_RECAPTCHA_V3,
            "websiteURL": site_url,
            "websiteKey": site_key,
            "pageAction": action,
            "minScore": min_score,
        }

        task_id = await self._create_task(task_data)
        solution = await self._get_task_result(task_id)

        return solution.get("gRecaptchaResponse", "")

    async def solve_turnstile(
        self,
        site_url: str,
        site_key: str,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None,
    ) -> str:
        """Solve a Cloudflare Turnstile challenge.

        Args:
            site_url: URL of the page where the CAPTCHA appears.
            site_key: Turnstile site key.
            user_agent: Browser user-agent string (optional).
            proxy: Proxy in ``user:pass@ip:port`` format (optional).

        Returns:
            The Turnstile response token.
        """
        task_data: Dict[str, Any] = {
            "type": self.TASK_TURNSTILE,
            "websiteURL": site_url,
            "websiteKey": site_key,
        }

        if user_agent:
            task_data["userAgent"] = user_agent

        if proxy:
            task_data["proxy"] = f"http://{proxy}"

        task_id = await self._create_task(task_data)
        solution = await self._get_task_result(task_id)

        return solution.get("token", "")

    async def solve_image(
        self,
        image_base64: Optional[str] = None,
        image_path: Optional[Path] = None,
        module: str = "common",
        case_sensitive: bool = False,
    ) -> str:
        """Solve an image-based CAPTCHA (OCR / image-to-text).

        Exactly one of *image_base64* or *image_path* must be provided.

        Args:
            image_base64: Base64-encoded image data.
            image_path: Filesystem path to an image file.
            module: Recognition module (``"common"``, ``"queueit"``,
                etc.).
            case_sensitive: Whether the answer is case-sensitive.

        Returns:
            The recognised CAPTCHA text.

        Raises:
            ValueError: If neither *image_base64* nor *image_path* is
                provided.
        """
        if image_base64 is None and image_path is None:
            raise ValueError(
                "Either image_base64 or image_path must be provided"
            )

        if image_path:
            import base64
            image_base64 = base64.b64encode(
                image_path.read_bytes()
            ).decode()

        task_data: Dict[str, Any] = {
            "type": self.TASK_IMAGE,
            "body": image_base64,
            "module": module,
            "case": case_sensitive,
        }

        task_id = await self._create_task(task_data)
        solution = await self._get_task_result(task_id)

        return solution.get("text", "")

    async def get_balance(self) -> float:
        """Retrieve the current CapSolver account balance.

        Returns:
            Account balance in USD.

        Raises:
            Exception: If the balance check API call fails.
        """
        await self._ensure_session()

        payload = {"clientKey": self.api_key}

        url = f"{self.BASE_URL}/getBalance"
        async with self.session.post(url, json=payload) as resp:
            data = await resp.json()

            if data.get("errorId") != 0:
                error_desc = data.get(
                    "errorDescription", "Unknown error"
                )
                raise Exception(
                    f"CapSolver balance check failed: {error_desc}"
                )

            balance = data.get("balance", 0.0)
            logger.info("CapSolver balance: $%.4f", balance)
            return balance


# Example usage
async def main() -> None:
    """Test the CapSolver client by checking the account balance."""
    import os

    api_key = os.getenv("CAPSOLVER_API_KEY")
    if not api_key:
        print("CAPSOLVER_API_KEY not set")
        return

    async with CapSolverClient(api_key) as solver:
        balance = await solver.get_balance()
        print(f"Balance: ${balance:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
