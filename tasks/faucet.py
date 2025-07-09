from utils.db_api_async.models import User
import aiohttp
import asyncio
from loguru import logger


class FaucetError(Exception):
    pass


class CaptchaUnsolvableError(FaucetError):
    pass


class RateLimitError(FaucetError):
    pass


class Faucet:
    def __init__(self, user: User, api_key: str):
        self.user = user
        self.api_key = api_key
        self.site_key = "5b86452e-488a-4f62-bd32-a332445e2f51"
        self.base_url = "https://faucet-go-production.up.railway.app/api/claim"
        self.captcha_url = "https://api.solvecaptcha.com"
        self.page_url = "https://faucet.campnetwork.xyz/"
        self.headers = {
            "User-Agent": f"{self.user.user_agent}",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": self.page_url,
            "Content-Type": "application/json",
            "Origin": "https://faucet.campnetwork.xyz",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "cross-site",
            "Priority": "u=4",
        }

    async def solve_captcha(self) -> str:
        """Solve hCaptcha using solvecaptcha service."""
        params = {
            "key": self.api_key,
            "method": "hcaptcha",
            "sitekey": self.site_key,
            "pageurl": self.page_url,
            "json": 1,
        }
        if self.user.proxy:
            params["proxy"] = self.user.proxy.split("//")[-1]
            params["proxytype"] = "HTTP"

        async with aiohttp.ClientSession() as session:
            try:
                # Submit captcha solving request
                async with session.get(
                    f"{self.captcha_url}/in.php", params=params
                ) as response:
                    if response.status != 200:
                        raise FaucetError(
                            f"Captcha submission failed: HTTP {response.status}"
                        )
                    data = await response.json()
                    if data.get("status") != 1:
                        raise FaucetError(
                            f"Captcha submission error: {data.get('request')}"
                        )
                    captcha_id = data.get("request")
                    logger.debug(
                        f"{self.user.public_key} success submit capthca solving request {captcha_id}"
                    )

                # Poll for captcha solution
                for _ in range(45):  # Max 3 minutes wait (30 * 6 seconds)
                    await asyncio.sleep(6)
                    async with session.get(
                        f"{self.captcha_url}/res.php",
                        params={
                            "key": self.api_key,
                            "action": "get",
                            "id": captcha_id,
                            "json": 1,
                        },
                    ) as response:
                        if response.status != 200:
                            raise FaucetError(
                                f"Captcha polling failed: HTTP {response.status}"
                            )
                        result = await response.json()
                        if result.get("status") == 1:
                            return result.get("request")
                        if result.get("request") != "CAPCHA_NOT_READY":
                            if result.get("request") == "ERROR_CAPTCHA_UNSOLVABLE":
                                raise CaptchaUnsolvableError(
                                    f"{self.user.public_key} Captcha unsolvable error"
                                )
                            raise FaucetError(
                                f"Captcha solving failed: {result.get('request')}"
                            )

                raise FaucetError("Captcha solving timeout")
            except aiohttp.ClientError as e:
                raise FaucetError(f"Network error during captcha solving: {str(e)}")

    async def claim_tokens(self) -> dict:
        """Claim tokens from faucet using solved captcha."""
        try:
            logger.info(f"{self.user.public_key} start faucet claim")
            captcha_response = await self.solve_captcha()
            logger.debug(f"{self.user} success get captcha token {captcha_response}")
            self.headers["h-captcha-response"] = captcha_response
            json_data = {"address": self.user.public_key}

            proxy = self.user.proxy if self.user.proxy else None
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url, headers=self.headers, json=json_data, proxy=proxy
                ) as response:
                    if response.status != 200:
                        logger.debug(
                            f"{self.user} request failed {response.status} {await response.text()}"
                        )
                        if response.status == 429:
                            raise RateLimitError(
                                f"{self.user.public_key} Rate limit exceeded: Tokens already claimed from this IP in last 24 hours"
                            )
                        raise FaucetError(
                            f"{self.user} Claim request failed: HTTP {response.status} {await response.text()}"
                        )
                    result = await response.json()
                    if "error" in result:
                        raise FaucetError(
                            f"{self.user} Faucet error: {result['error']}"
                        )
                    logger.success(f"{self.user} success faucet claim")
                    return result
        except aiohttp.ClientError as e:
            raise FaucetError(f"Network error during claim: {str(e)}")
