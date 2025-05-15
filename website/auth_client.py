import json
import asyncio
import random
from datetime import datetime
from typing import Dict, Optional, Tuple
from loguru import logger
from eth_account.messages import encode_defunct
from libs.eth_async.client import Client
from .http_client import BaseHttpClient
from .captcha_handler import CloudflareHandler


class AuthClient(BaseHttpClient):
    """Клиент для авторизации на CampNetwork"""
    
    # URL для авторизации
    BASE_URL = "https://loyalty.campnetwork.xyz"
    AUTH_CSRF_URL = f"{BASE_URL}/api/auth/csrf"
    AUTH_CALLBACK_URL = f"{BASE_URL}/api/auth/callback/credentials"
    AUTH_SESSION_URL = f"{BASE_URL}/api/auth/session"
    AUTH_SIGNOUT_URL = f"{BASE_URL}/api/auth/signout"
    DYNAMIC_CONNECT_URL = "https://app.dynamicauth.com/api/v0/sdk/09a766ae-a662-4d96-904a-28d1c9e4b587/connect"
    DYNAMIC_NONCE_URL = "https://app.dynamicauth.com/api/v0/sdk/09a766ae-a662-4d96-904a-28d1c9e4b587/nonce"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.client = Client(
            private_key=self.user.private_key,
            proxy=self.user.proxy
        )
        self.cloudflare = CloudflareHandler(self)
        
        # Данные авторизации
        self.csrf_token = None
        self.nonce = None
        self.session_data = None
        self.user_id = None
    
    async def initial_request(self) -> bool:
        """
        Выполняет начальный запрос для проверки наличия Cloudflare защиты
        
        Returns:
            Статус успеха
        """
        try:
            logger.info(f"{self.user} выполняю начальный запрос для проверки Cloudflare защиты")
            
            # Проверяем наличие Cloudflare защиты
            
            success, response = await self.request(
                url=f"{self.BASE_URL}/home",
                method="GET",
                check_cloudflare=True  # Включаем автоматическую проверку и обработку Cloudflare
            )
            if success:
                logger.success(f"{self.user} начальный запрос успешен")
                return True
            else:
                logger.error(f"{self.user} не удалось выполнить начальный запрос")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при выполнении начального запроса: {str(e)}")
            return False
    
    async def connect_wallet(self) -> bool:
        """
        Первый этап авторизации - подключение кошелька через Dynamic Auth
        
        Returns:
            Статус успеха
        """
        json_data = {
            'address': f'{self.user.public_key}',
            'chain': 'EVM',
            'provider': 'browserExtension',
            'walletName': 'rabby',
            'authMode': 'connect-only',
        }
        
        headers = await self.get_headers({
            'Content-Type': 'application/json',
            'x-dyn-version': 'WalletKit/3.9.11',
            'x-dyn-api-version': 'API/0.0.586',
            'Origin': 'https://loyalty.campnetwork.xyz',
        })
        
        success, response = await self.request(
            url=self.DYNAMIC_CONNECT_URL,
            method="POST",
            json_data=json_data,
            headers=headers
        )
        
        if success:
            logger.info(f"{self.user} успешно подключил кошелек")
            return True
        else:
            logger.error(f"{self.user} не удалось подключить кошелек: {response}")
            return False
    
    async def get_nonce(self) -> bool:
        """
        Получает nonce для авторизации
        
        Returns:
            Статус успеха
        """
        headers = await self.get_headers({
            'x-dyn-version': 'WalletKit/3.9.11',
            'x-dyn-api-version': 'API/0.0.586',
        })
        
        success, response = await self.request(
            url=self.DYNAMIC_NONCE_URL,
            method="GET",
            headers=headers
        )
        
        if success and isinstance(response, dict) and 'nonce' in response:
            self.nonce = response['nonce']
            logger.info(f"{self.user} получил nonce: {self.nonce[:10]}...")
            return True
        else:
            logger.error(f"{self.user} не удалось получить nonce: {response}")
            return False
    
    async def get_csrf_token(self) -> bool | str:
        """
        Получает CSRF токен с проверкой на ограничение запросов
        
        Returns:
            Статус успеха или строка с кодом ошибки
        """
        headers = await self.get_headers({
            'Content-Type': 'application/json',
            'Referer': 'https://loyalty.campnetwork.xyz/home',
            'Origin': 'https://loyalty.campnetwork.xyz',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        success, response = await self.request(
            url=self.AUTH_CSRF_URL,
            method="GET",
            headers=headers
        )
        
        if success and isinstance(response, dict) and 'csrfToken' in response:
            self.csrf_token = response['csrfToken']
            logger.info(f"{self.user} получил CSRF токен: {self.csrf_token[:10]}...")
            return True
        else:
            # Проверяем на ошибку о превышении лимита запросов
            if isinstance(response, dict) and response.get("message") == "Too many requests, please try again later.":
                logger.warning(f"{self.user} превышен лимит запросов при получении CSRF токена")
                return "RATE_LIMIT"
            else:
                logger.error(f"{self.user} не удалось получить CSRF токен: {response}")
                return False

    async def sign_message(self) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Подписывает сообщение для авторизации
        
        Returns:
            (message, signature): Сообщение и подпись
        """
        if not self.nonce:
            logger.error(f"{self.user} попытка подписать сообщение без nonce")
            return None, None
            
        try:
            # Текущая дата и время в формате ISO
            current_time = datetime.utcnow().isoformat('T') + 'Z'
            
            # Создаем сообщение для подписи
            message = {
                "domain": "loyalty.campnetwork.xyz",
                "address": self.user.public_key,
                "statement": "Sign in to the app. Powered by Snag Solutions.",
                "uri": "https://loyalty.campnetwork.xyz",
                "version": "1",
                "chainId": 1,
                "nonce": self.nonce,
                "issuedAt": current_time
            }
            
            # Создаем строковое представление сообщения в формате EIP-191
            message_str = (
                f"loyalty.campnetwork.xyz wants you to sign in with your Ethereum account:\n"
                f"{message['address']}\n\n"
                f"{message['statement']}\n\n"
                f"URI: {message['uri']}\n"
                f"Version: {message['version']}\n"
                f"Chain ID: {message['chainId']}\n"
                f"Nonce: {message['nonce']}\n"
                f"Issued At: {message['issuedAt']}"
            )
            
            # Кодируем сообщение для подписи
            message_bytes = encode_defunct(text=message_str)
            
            # Подписываем сообщение
            sign = self.client.account.sign_message(message_bytes)
            signature = sign.signature.hex()
            
            logger.info(f"{self.user} успешно подписал сообщение")
            
            return message, signature
            
        except Exception as e:
            logger.error(f"{self.user} ошибка при подписании сообщения: {str(e)}")
            return None, None
    
    async def authenticate(self) -> bool:
        """
        Авторизация с использованием подписанного сообщения
        
        Returns:
            Статус успеха
        """
        if not self.csrf_token or not self.nonce:
            logger.error(f"{self.user} попытка аутентификации без CSRF токена или nonce")
            return False
            
        # Подписываем сообщение
        message, signature = await self.sign_message()
        if not message or not signature:
            return False
            
        # Формируем данные формы для запроса
        form_data = {
            'message': json.dumps(message),
            'accessToken': signature,
            'signature': signature,
            'walletConnectorName': 'Rabby',
            'walletAddress': self.user.public_key,
            'redirect': 'false',
            'callbackUrl': '/protected',
            'chainType': 'evm',
            'csrfToken': self.csrf_token,
            'json': 'true'
        }
        
        headers = await self.get_headers({
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://loyalty.campnetwork.xyz/home',
            'Origin': 'https://loyalty.campnetwork.xyz',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        success, response = await self.request(
            url=self.AUTH_CALLBACK_URL,
            method="POST",
            data=form_data,
            headers=headers
        )
        
        if success:
            # Проверяем наличие токена сессии в куках
            if '__Secure-next-auth.session-token' in self.cookies:
                logger.success(f"{self.user} успешно авторизован")
                return True
        
        logger.error(f"{self.user} не удалось авторизоваться: {response}")
        return False
    
    async def get_session_info(self) -> bool:
        """
        Получает информацию о текущей сессии
        
        Returns:
            Статус успеха
        """
        if '__Secure-next-auth.session-token' not in self.cookies:
            logger.error(f"{self.user} попытка получить информацию о сессии без токена")
            return False
            
        headers = await self.get_headers({
            'Content-Type': 'application/json',
            'Referer': 'https://loyalty.campnetwork.xyz/home',
            'Sec-Fetch-Site': 'same-origin',
        })
        
        success, response = await self.request(
            url=self.AUTH_SESSION_URL,
            method="GET",
            headers=headers
        )
        
        if success and isinstance(response, dict) and 'user' in response and 'id' in response['user']:
            self.session_data = response
            self.user_id = response['user']['id']
            logger.info(f"{self.user} получил информацию о сессии, ID пользователя: {self.user_id}")
            return True
        else:
            logger.error(f"{self.user} не удалось получить информацию о сессии: {response}")
            return False

    async def login(self) -> bool:
        """
        Полный процесс авторизации с обработкой ограничения запросов
        
        Returns:
            Статус успеха
        """
        try:
            # Шаг 1: Начальный запрос и обработка Cloudflare
            if not await self.initial_request():
                return False
                
            # Шаг 2: Подключаем кошелек
            if not await self.connect_wallet():
                return False
                
            # Шаг 3: Получаем nonce
            if not await self.get_nonce():
                return False
                
            # Шаг 4: Получаем CSRF токен с обработкой ограничения запросов
            csrf_result = await self.get_csrf_token()
            
            # Если получили ошибку о слишком частых запросах - добавляем обработку
            if csrf_result == "RATE_LIMIT":
                # Ставим аккаунт в таймаут на 5-10 минут (300-600 секунд)
                timeout_duration = random.uniform(300, 600)
                logger.warning(f"{self.user} достигнут лимит запросов, ожидаем {int(timeout_duration)} секунд перед повторной попыткой")
                await asyncio.sleep(timeout_duration)
                
                # Повторяем попытку получения CSRF токена
                if not await self.get_csrf_token():
                    return False
            elif not csrf_result:
                return False
                
            # Шаг 5: Аутентифицируемся с подписанным сообщением
            if not await self.authenticate():
                return False
                
            # Шаг 6: Получаем информацию о сессии
            if not await self.get_session_info():
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"{self.user} ошибка в процессе авторизации: {str(e)}")
            return False
