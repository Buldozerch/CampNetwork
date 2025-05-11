import asyncio
import aiohttp
import json
import base64
import urllib.parse
from typing import Dict, Optional, Tuple
from loguru import logger
from urllib.parse import urlparse
from data.config import CAPMONSTER_API_KEY


class CloudflareHandler:
    """Обработчик Cloudflare Turnstile защиты"""
    
    def __init__(self, http_client):
        """
        Инициализация обработчика Cloudflare
        
        Args:
            http_client: HTTP-клиент для выполнения запросов
        """
        self.http_client = http_client
    
    async def parse_proxy(self) -> Tuple[Optional[str], Optional[int], Optional[str], Optional[str]]:
        """
        Парсит строку прокси в составляющие компоненты
        
        Returns:
            Tuple[ip, port, login, password]
        """
        if not self.http_client.user.proxy:
            return None, None, None, None
            
        parsed = urlparse(self.http_client.user.proxy)
        
        ip = parsed.hostname
        port = parsed.port
        login = parsed.username
        password = parsed.password
        
        return ip, port, login, password
    
    def encode_html_to_base64(self, html_content: str) -> str:
        """
        Кодирует HTML в base64
        
        Args:
            html_content: HTML-контент для кодирования
            
        Returns:
            HTML, закодированный в base64
        """
        # Эквивалент encodeURIComponent в JavaScript
        encoded = urllib.parse.quote(html_content)
        
        # Эквивалент unescape в JavaScript (замена %xx последовательностей)
        unescaped = urllib.parse.unquote(encoded)
        
        # Эквивалент btoa в JavaScript
        base64_encoded = base64.b64encode(unescaped.encode('latin1')).decode('ascii')
        
        return base64_encoded
    
    async def get_recaptcha_task(self, html: str) -> Optional[int]:
        """
        Создает задачу на решение Cloudflare Turnstile в CapMonster
        
        Args:
            html: HTML-страница с капчей
            
        Returns:
            ID задачи или None в случае ошибки
        """
        try:
            # Парсинг прокси
            ip, port, login, password = await self.parse_proxy()
            
            # Кодируем HTML в base64
            html_base64 = self.encode_html_to_base64(html)           
            windows_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            
            # Данные для запроса к CapMonster
            json_data = {
                "clientKey": CAPMONSTER_API_KEY,
                "task": {
                    "type": "TurnstileTask",
                    "websiteURL": "https://loyalty.campnetwork.xyz/home",
                    "websiteKey": "0x4AAAAAAADnPIDROrmt1Wwj",
                    "cloudflareTaskType": "cf_clearance",  # Нужен cf_clearance cookie
                    "htmlPageBase64": html_base64,
                    "userAgent": windows_user_agent
                }
            }
            
            # Добавляем данные прокси, если они есть
            if ip and port:
                json_data["task"].update({
                    "proxyType": "http",
                    "proxyAddress": ip,
                    "proxyPort": port
                })
                
                if login and password:
                    json_data["task"].update({
                        "proxyLogin": login,
                        "proxyPassword": password
                    })
                    
            # Создаем новую сессию
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url='https://api.capmonster.cloud/createTask',
                    json=json_data
                ) as resp:
                    if resp.status == 200:
                        result = await resp.text()
                        result = json.loads(result)               
                        if result.get('errorId') == 0:
                            logger.info(f"{self.http_client.user} создана задача в CapMonster: {result['taskId']}")
                            return result['taskId']
                        else:
                            logger.error(f"{self.http_client.user} ошибка CapMonster: {result.get('errorDescription', 'Unknown error')}")
                            return None
                    else:
                        logger.error(f"{self.http_client.user} ошибка запроса к CapMonster: {resp.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"{self.http_client.user} ошибка при создании задачи в CapMonster: {str(e)}")
            return None
    
    async def get_recaptcha_token(self, task_id: int) -> Optional[str]:
        """
        Получает результат решения задачи от CapMonster
        
        Args:
            task_id: ID задачи
            
        Returns:
            Токен cf_clearance или None в случае ошибки
        """
        json_data = {
            "clientKey": CAPMONSTER_API_KEY,
            "taskId": task_id
        }
        
        # Максимальное время ожидания (60 секунд)
        max_attempts = 60
        
        for i in range(max_attempts):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url='https://api.capmonster.cloud/getTaskResult',
                        json=json_data
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.text()
                            result = json.loads(result)                 
                            if result['status'] == 'ready':
                                # Получаем cf_clearance из решения
                                if 'solution' in result:
                                    cf_clearance = result['solution'].get('cf_clearance') or result['solution'].get('token')
                                    logger.success(f"{self.http_client.user} получен cf_clearance токен")
                                    return cf_clearance
                                    
                                logger.error(f"{self.http_client.user} решение не содержит cf_clearance")
                                return None
                                
                            elif result['status'] == 'processing':
                                # Если задача еще решается, ждем 1 секунду
                                await asyncio.sleep(1)
                                continue
                            else:
                                logger.error(f"{self.http_client.user} неизвестный статус задачи: {result['status']}")
                                return None
                        else:
                            logger.error(f"{self.http_client.user} ошибка при получении результата: {resp.status}")
                            await asyncio.sleep(2)
                            continue
                            
            except Exception as e:
                logger.error(f"{self.http_client.user} ошибка при получении результата: {str(e)}")
                return None
                
        logger.error(f"{self.http_client.user} превышено время ожидания решения от CapMonster")
        return None
    
    async def recaptcha_handle(self, html: str) -> Optional[str]:
        """
        Обрабатывает Cloudflare Turnstile captcha через CapMonster
        
        Args:
            html: HTML-страница с капчей
            
        Returns:
            Токен cf_clearance или None в случае ошибки
        """
        max_retry = 10
        captcha_token = None
        
        for i in range(max_retry):
            try:
                # Получаем задание на решение Turnstile
                task = await self.get_recaptcha_task(html=html)
                if not task:
                    logger.error(f"{self.http_client.user} не удалось создать задачу в CapMonster, попытка {i+1}/{max_retry}")
                    await asyncio.sleep(2)
                    continue
                
                # Получаем результат решения
                result = await self.get_recaptcha_token(task_id=task)
                if result:
                    captcha_token = result
                    logger.success(f"{self.http_client.user} успешно получен токен капчи")
                    break
                else:
                    logger.warning(f"{self.http_client.user} не удалось получить токен, попытка {i+1}/{max_retry}")
                    await asyncio.sleep(3)
                    continue
                    
            except Exception as e:
                logger.error(f"{self.http_client.user} ошибка при обработке капчи: {str(e)}")
                await asyncio.sleep(3)
                continue
                    
        return captcha_token
    
    async def handle_cloudflare_protection(self, url: str, method: str = "GET") -> Tuple[bool, Optional[str]]:
        """
        Обрабатывает защиту Cloudflare
        
        Args:
            url: URL для запроса
            method: Метод запроса
            
        Returns:
            (bool, cf_clearance): Статус успеха и токен cf_clearance
        """
        try:
            logger.info(f"{self.http_client.user} проверка наличия Cloudflare Turnstile защиты")
            
            # Делаем начальный запрос для проверки наличия Cloudflare
            success, response = await self.http_client.request(url=url, method=method)
            
            # Если запрос успешен, защиты нет
            if success:
                logger.info(f"{self.http_client.user} защита Cloudflare отсутствует или уже обойдена")
                return True, None
                
            # Если запрос вернул HTML с Cloudflare, решаем капчу
            logger.info(f"{self.http_client.user} обнаружена защита Cloudflare, начинаю решение капчи")
            
            # Решаем капчу
            cf_clearance = await self.recaptcha_handle(html=response)
            
            if cf_clearance:
                # Добавляем токен в cookies
                self.http_client.cookies['cf_clearance'] = cf_clearance
                
                # Повторяем запрос с токеном
                logger.info(f"{self.http_client.user} повторный запрос с токеном cf_clearance")
                windows_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
                
                # Важно: cf_clearance привязан к User-Agent, поэтому используем тот же User-Agent
                success, response = await self.http_client.request(
                    url=url, 
                    method=method,
                    headers={'User-Agent': windows_user_agent}
                )
                
                if success:
                    logger.success(f"{self.http_client.user} защита Cloudflare успешно обойдена")
                    return True, cf_clearance
                else:
                    logger.error(f"{self.http_client.user} не удалось обойти защиту Cloudflare: {response}")
                    return False, None
            else:
                logger.error(f"{self.http_client.user} не удалось получить токен cf_clearance")
                return False, None
                    
            
        except Exception as e:
            logger.error(f"{self.http_client.user} ошибка при обработке Cloudflare защиты: {str(e)}")
            return False, None
