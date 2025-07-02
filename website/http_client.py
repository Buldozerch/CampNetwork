from curl_cffi.requests import AsyncSession
from curl_cffi import CurlError
import asyncio
import random
import json
import aiohttp
from typing import Dict, Tuple, Union, Optional
from loguru import logger
from website.captcha_handler import CloudflareHandler
from utils.db_api_async.db_api import Session
from utils.db_api_async.models import User
from data.config import ACTUAL_UA
from data.models import Settings


class BaseHttpClient:
    """Базовый HTTP-клиент для выполнения запросов"""

    def __init__(self, user: User):
        """
        Инициализация базового HTTP-клиента

        Args:
            user: Пользователь с приватным ключом и прокси
        """
        self.user = user
        self.cookies = {}
        # Счетчик ошибок прокси
        self.proxy_errors = 0
        # Счетчик ошибок капчи
        self.captcha_errors = 0
        # Настройки для автоматической обработки ошибок ресурсов
        self.settings = Settings()
        self.max_proxy_errors = self.settings.resources_max_failures
        # Инициализируем обработчик Cloudflare
        self.cloudflare_handler = CloudflareHandler(self)
        # Время последнего решения капчи
        self.last_captcha_time = None
        # Максимальное время жизни капчи (20 минут)
        self.captcha_lifetime = 20 * 60

    def _is_captcha_expired(self) -> bool:
        """
        Проверяет, истек ли срок действия капчи

        Returns:
            True, если капча истекла или не была решена
        """
        import time

        if not self.last_captcha_time:
            return True

        return (time.time() - self.last_captcha_time) > self.captcha_lifetime

    def _update_captcha_time(self):
        """Обновляет время последнего решения капчи"""
        import time

        self.last_captcha_time = time.time()

    async def handle_captcha_if_needed(self, url: str, response_text: str) -> bool:
        """
        Проверяет, требуется ли решение капчи, и решает ее при необходимости

        Args:
            url: URL запроса
            response_text: Текст ответа

        Returns:
            True, если капча была успешно решена
        """
        # Проверяем признаки Cloudflare защиты
        logger.info(f"{self.user} обнаружена Cloudflare капча, начинаю решение")

        # Решаем капчу
        success = await self.cloudflare_handler.handle_cloudflare_protection(
            html=response_text
        )

        if success:
            # Обновляем время последнего решения капчи
            self._update_captcha_time()
            return True
        else:
            return False

    async def get_headers(self, additional_headers: Optional[Dict] = None) -> Dict:
        """
        Создает базовые заголовки для запросов

        Args:
            additional_headers: Дополнительные заголовки

        Returns:
            Сформированные заголовки
        """
        base_headers = {
            "User-Agent": ACTUAL_UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Referer": "https://loyalty.campnetwork.xyz/",
            "DNT": "1",
            "Sec-GPC": "1",
            "Connection": "keep-alive",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Priority": "u=4",
        }

        if additional_headers:
            base_headers.update(additional_headers)

        return base_headers

    async def request(
        self,
        url: str,
        method: str,
        data: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        timeout: int = 30,
        retries: int = 5,
        extra_cookies: bool = False,
        allow_redirects: bool = True,
        check_cloudflare: bool = True,  # Флаг для проверки Cloudflare защиты
    ) -> Tuple[bool, Union[Dict, str]]:
        """
        Выполняет HTTP-запрос с автоматической обработкой капчи и ошибок прокси

        Args:
            url: URL для запроса
            method: Метод запроса (GET, POST, etc.)
            data: Данные формы
            json_data: JSON данные
            params: Параметры URL
            headers: Дополнительные заголовки
            timeout: Таймаут запроса в секундах
            retries: Количество повторных попыток
            extra_cookies: Использовать дополнительные cookies
            allow_redirects: Следовать ли за редиректами
            check_cloudflare: Проверять и обрабатывать Cloudflare защиту

        Returns:
            (bool, data): Статус успеха и данные ответа
        """
        base_headers = await self.get_headers(headers)

        # Настраиваем параметры запроса
        request_kwargs = {
            "url": url,
            "proxy": self.user.proxy,
            "headers": base_headers,
            "cookies": self.cookies,
            "timeout": timeout,
            "allow_redirects": allow_redirects,
        }
        if not extra_cookies:
            self.cookies["accountLinkData"] = ""
        if not extra_cookies and self.cookies.get("__cf_bm"):
            self.cookies.pop("__cf_bm")
        # Добавляем опциональные параметры
        if json_data is not None:
            request_kwargs["json"] = json_data
        if data is not None:
            request_kwargs["data"] = data
        if params is not None:
            request_kwargs["params"] = params

        proxy_error_occurred = False
        captcha_error_occurred = False

        # Выполняем запрос с повторными попытками
        for attempt in range(retries):
            try:
                async with AsyncSession(impersonate="chrome") as session:
                    resp = await getattr(session, method.lower())(**request_kwargs)
                    # Сохраняем cookies из ответа
                    if resp.cookies:
                        for name, cookie in resp.cookies.items():
                            self.cookies[name] = cookie

                    if 300 <= resp.status_code < 400 and not allow_redirects:
                        headers_dict = dict(resp.headers)
                        return (
                            False,
                            headers_dict,
                        )  # Возвращаем заголовки вместо тела ответа

                    # Успешный ответ
                    if resp.status_code == 200 or resp.status_code == 202:
                        # Сбрасываем счетчик ошибок прокси при успешном запросе
                        self.proxy_errors = 0
                        self.captcha_errors = 0
                        try:
                            json_resp = resp.json()
                            return True, json_resp
                        except Exception:
                            return True, resp.text

                    # Получаем текст ответа для анализа
                    response_text = resp.text

                    # Проверяем наличие Cloudflare защиты в ответе
                    if check_cloudflare and ("Just a moment" in response_text):
                        logger.warning(
                            f"{self.user} обнаружена Cloudflare защита, попытка решения капчи..."
                        )
                        captcha_error_occurred = True

                        # Решаем капчу
                        captcha_solved = await self.handle_captcha_if_needed(
                            url, response_text
                        )

                        if captcha_solved:
                            # Если капча решена успешно, повторяем запрос
                            continue
                        else:
                            self.captcha_errors += 1
                            if self.captcha_errors >= 3:
                                logger.error(
                                    f"{self.user} не удалось решить капчу после {self.captcha_errors} попыток"
                                )
                                return False, "CAPTCHA_FAILED"

                            # Делаем паузу перед следующей попыткой
                            await asyncio.sleep(2**attempt)
                            continue

                    # Обработка ошибок
                    if 400 <= resp.status_code < 500:
                        logger.warning(
                            f"{self.user} получен статус {resp.status_code} при запросе {url}"
                        )

                        # Проверяем, может быть проблема с авторизацией
                        if resp.status_code == 401 or resp.status_code == 403:
                            if "!DOCTYPE" not in response_text:
                                logger.error(
                                    f"{self.user} ошибка авторизации: {response_text}"
                                )
                            return False, response_text

                        # Проверяем на ограничение запросов
                        if resp.status_code == 429:
                            logger.warning(f"{self.user} превышен лимит запросов (429)")

                            # Если это не последняя попытка, делаем большую задержку и пробуем снова
                            if attempt < retries - 1:
                                wait_time = random.uniform(10, 30)  # 10-30 секунд
                                logger.info(
                                    f"{self.user} ожидание {int(wait_time)} секунд перед следующей попыткой"
                                )
                                await asyncio.sleep(wait_time)
                                continue

                            # Парсим ответ, чтобы получить возможный JSON с сообщением об ошибке
                            try:
                                error_json = json.loads(response_text)
                                return False, error_json
                            except:
                                return False, "RATE_LIMIT"

                        # Парсим ответ, чтобы получить возможный JSON с сообщением об ошибке
                        try:
                            error_json = json.loads(response_text)
                            return False, error_json
                        except:
                            return False, response_text

                    elif 500 <= resp.status_code < 600:
                        logger.warning(
                            f"{self.user} получен статус {resp.status_code}, повторная попытка {attempt + 1}/{retries}"
                        )
                        await asyncio.sleep(2**attempt)  # Экспоненциальная задержка
                        continue

                    return False, response_text

            except CurlError as e:
                logger.warning(
                    f"{self.user} ошибка соединения при запросе {url}: {str(e)}"
                )

                # Увеличиваем счетчик ошибок прокси
                if (
                    "proxy" in str(e).lower()
                    or "connection" in str(e).lower()
                    or "connect" in str(e).lower()
                ):
                    self.proxy_errors += 1
                    proxy_error_occurred = True

                    # Если превышен лимит ошибок, отмечаем прокси как плохое
                    if self.proxy_errors >= self.max_proxy_errors:
                        logger.warning(
                            f"{self.user} превышен лимит ошибок прокси ({self.proxy_errors}/{self.max_proxy_errors}), отмечаем как BAD"
                        )
                        from .resource_manager import ResourceManager

                        resource_manager = ResourceManager()
                        await resource_manager.mark_proxy_as_bad(self.user.id)

                        # Если включена автозамена, пробуем заменить прокси
                        if self.settings.resources_auto_replace:
                            success, message = await resource_manager.replace_proxy(
                                self.user.id
                            )
                            if success:
                                logger.info(
                                    f"{self.user} прокси заменено автоматически: {message}"
                                )
                                # Обновляем прокси для текущего клиента
                                async with Session() as session:
                                    updated_user = await session.get(User, self.user.id)
                                    if updated_user:
                                        self.user.proxy = updated_user.proxy
                                        # Обновляем прокси в параметрах запроса
                                        request_kwargs["proxy"] = self.user.proxy
                                        # Сбрасываем счетчик ошибок
                                        self.proxy_errors = 0
                            else:
                                logger.error(
                                    f"{self.user} не удалось заменить прокси: {message}"
                                )

                await asyncio.sleep(2**attempt)  # Экспоненциальная задержка
                continue
            except Exception as e:
                logger.error(
                    f"{self.user} неожиданная ошибка при запросе {url}: {str(e)}"
                )
                return False, str(e)
