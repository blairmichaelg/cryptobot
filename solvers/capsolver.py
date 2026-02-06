"""
CapSolver API client for CAPTCHA solving.
Supports hCaptcha, reCaptcha v2/v3, Turnstile, image CAPTCHAs.

Issue #87: Alternative provider for hCaptcha when 2Captcha fails.
"""
import asyncio
import aiohttp
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class CapSolverClient:
    """
    CapSolver API client with async support.
    
    Docs: https://docs.capsolver.com/
    """
    
    BASE_URL = "https://api.capsolver.com"
    
    # Task types
    TASK_HCAPTCHA = "HCaptchaTaskProxyless"
    TASK_RECAPTCHA_V2 = "ReCaptchaV2TaskProxyless"
    TASK_RECAPTCHA_V3 = "ReCaptchaV3TaskProxyless"
    TASK_TURNSTILE = "AntiCloudflareTask"
    TASK_IMAGE = "ImageToTextTask"
    
    def __init__(self, api_key: str, polling_interval: float = 3.0, timeout: int = 180):
        """
        Initialize CapSolver client.
        
        Args:
            api_key: CapSolver API key
            polling_interval: Seconds between status checks (default 3)
            timeout: Maximum seconds to wait for solution (default 180)
        """
        self.api_key = api_key
        self.polling_interval = polling_interval
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if not self.session:
            self.session = aiohttp.ClientSession()
    
    async def _create_task(self, task_data: Dict[str, Any]) -> str:
        """
        Create CAPTCHA task.
        
        Args:
            task_data: Task configuration
            
        Returns:
            Task ID
            
        Raises:
            Exception: If task creation fails
        """
        await self._ensure_session()
        
        payload = {
            "clientKey": self.api_key,
            "task": task_data
        }
        
        logger.debug(f"Creating CapSolver task: {task_data.get('type')}")
        
        async with self.session.post(f"{self.BASE_URL}/createTask", json=payload) as resp:
            data = await resp.json()
            
            if data.get("errorId") != 0:
                error_code = data.get("errorCode", "UNKNOWN")
                error_desc = data.get("errorDescription", "No description")
                raise Exception(f"CapSolver task creation failed: {error_code} - {error_desc}")
            
            task_id = data.get("taskId")
            logger.info(f"CapSolver task created: {task_id}")
            return task_id
    
    async def _get_task_result(self, task_id: str) -> Dict[str, Any]:
        """
        Get task result with polling.
        
        Args:
            task_id: Task ID from _create_task
            
        Returns:
            Task solution data
            
        Raises:
            TimeoutError: If solution not ready within timeout
            Exception: If task fails
        """
        await self._ensure_session()
        
        payload = {
            "clientKey": self.api_key,
            "taskId": task_id
        }
        
        start_time = asyncio.get_event_loop().time()
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.timeout:
                raise TimeoutError(f"CapSolver task {task_id} timed out after {self.timeout}s")
            
            async with self.session.post(f"{self.BASE_URL}/getTaskResult", json=payload) as resp:
                data = await resp.json()
                
                if data.get("errorId") != 0:
                    error_code = data.get("errorCode", "UNKNOWN")
                    error_desc = data.get("errorDescription", "No description")
                    raise Exception(f"CapSolver task failed: {error_code} - {error_desc}")
                
                status = data.get("status")
                
                if status == "ready":
                    solution = data.get("solution", {})
                    logger.info(f"CapSolver task {task_id} solved in {elapsed:.1f}s")
                    return solution
                
                elif status == "failed":
                    raise Exception(f"CapSolver task {task_id} failed")
                
                # Status is "processing", wait and retry
                logger.debug(f"CapSolver task {task_id} still processing ({elapsed:.1f}s elapsed)")
                await asyncio.sleep(self.polling_interval)
    
    async def solve_hcaptcha(
        self,
        site_url: str,
        site_key: str,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None
    ) -> str:
        """
        Solve hCaptcha.
        
        Args:
            site_url: URL where CAPTCHA appears
            site_key: hCaptcha site key
            user_agent: Browser user agent (optional)
            proxy: Proxy string format "user:pass@ip:port" (optional)
            
        Returns:
            hCaptcha token
        """
        task_data = {
            "type": self.TASK_HCAPTCHA,
            "websiteURL": site_url,
            "websiteKey": site_key
        }
        
        if user_agent:
            task_data["userAgent"] = user_agent
        
        if proxy:
            # CapSolver uses proxy format: protocol://user:pass@ip:port
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
        invisible: bool = False
    ) -> str:
        """
        Solve reCaptcha v2.
        
        Args:
            site_url: URL where CAPTCHA appears
            site_key: reCaptcha site key
            user_agent: Browser user agent (optional)
            proxy: Proxy string format "user:pass@ip:port" (optional)
            invisible: Whether this is invisible reCaptcha (default False)
            
        Returns:
            reCaptcha token
        """
        task_data = {
            "type": self.TASK_RECAPTCHA_V2,
            "websiteURL": site_url,
            "websiteKey": site_key
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
        min_score: float = 0.7
    ) -> str:
        """
        Solve reCaptcha v3.
        
        Args:
            site_url: URL where CAPTCHA appears
            site_key: reCaptcha site key
            action: reCaptcha action (default "submit")
            min_score: Minimum score required (default 0.7)
            
        Returns:
            reCaptcha token
        """
        task_data = {
            "type": self.TASK_RECAPTCHA_V3,
            "websiteURL": site_url,
            "websiteKey": site_key,
            "pageAction": action,
            "minScore": min_score
        }
        
        task_id = await self._create_task(task_data)
        solution = await self._get_task_result(task_id)
        
        return solution.get("gRecaptchaResponse", "")
    
    async def solve_turnstile(
        self,
        site_url: str,
        site_key: str,
        user_agent: Optional[str] = None,
        proxy: Optional[str] = None
    ) -> str:
        """
        Solve Cloudflare Turnstile.
        
        Args:
            site_url: URL where CAPTCHA appears
            site_key: Turnstile site key
            user_agent: Browser user agent (optional)
            proxy: Proxy string format "user:pass@ip:port" (optional)
            
        Returns:
            Turnstile token
        """
        task_data = {
            "type": self.TASK_TURNSTILE,
            "websiteURL": site_url,
            "websiteKey": site_key
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
        case_sensitive: bool = False
    ) -> str:
        """
        Solve image CAPTCHA.
        
        Args:
            image_base64: Base64 encoded image (mutually exclusive with image_path)
            image_path: Path to image file (mutually exclusive with image_base64)
            module: Recognition module ("common", "queueit", etc.)
            case_sensitive: Whether answer is case sensitive
            
        Returns:
            CAPTCHA text
        """
        if image_base64 is None and image_path is None:
            raise ValueError("Either image_base64 or image_path must be provided")
        
        if image_path:
            import base64
            image_base64 = base64.b64encode(image_path.read_bytes()).decode()
        
        task_data = {
            "type": self.TASK_IMAGE,
            "body": image_base64,
            "module": module,
            "case": case_sensitive
        }
        
        task_id = await self._create_task(task_data)
        solution = await self._get_task_result(task_id)
        
        return solution.get("text", "")
    
    async def get_balance(self) -> float:
        """
        Get account balance.
        
        Returns:
            Balance in USD
        """
        await self._ensure_session()
        
        payload = {"clientKey": self.api_key}
        
        async with self.session.post(f"{self.BASE_URL}/getBalance", json=payload) as resp:
            data = await resp.json()
            
            if data.get("errorId") != 0:
                error_desc = data.get("errorDescription", "Unknown error")
                raise Exception(f"CapSolver balance check failed: {error_desc}")
            
            balance = data.get("balance", 0.0)
            logger.info(f"CapSolver balance: ${balance:.4f}")
            return balance


# Example usage
async def main():
    """Test CapSolver client."""
    import os
    
    api_key = os.getenv("CAPSOLVER_API_KEY")
    if not api_key:
        print("❌ CAPSOLVER_API_KEY not set")
        return
    
    async with CapSolverClient(api_key) as solver:
        # Get balance
        balance = await solver.get_balance()
        print(f"Balance: ${balance:.4f}")
        
        # Test hCaptcha (example)
        # token = await solver.solve_hcaptcha(
        #     site_url="https://example.com",
        #     site_key="10000000-ffff-ffff-ffff-000000000001"
        #)
        # print(f"Token: {token[:50]}...")


if __name__ == "__main__":
    asyncio.run(main())
