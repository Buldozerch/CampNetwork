import asyncio
import random
from typing import Dict, List, Optional, Union, Any, Tuple, Tuple, Tuple, Tuple
from loguru import logger
import twitter  # Import tweepy-self library
from twitter.utils import remove_at_sign
from utils.db_api_async.models import User
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from website.resource_manager import ResourceManager
from website.http_client import BaseHttpClient
from data.config import CAPMONSTER_API_KEY, ACTUAL_UA
from data.models import Settings


class TwitterClient(BaseHttpClient):
    """Клиент для взаимодействия с Twitter API"""

    # URLs для запросов
    BASE_URL = "https://loyalty.campnetwork.xyz"
    TWITTER_CONNECT_URL = f"{BASE_URL}/api/loyalty/social/connect/twitter"
    TWITTER_VERIFY_URL = f"{BASE_URL}/api/loyalty/social/verify/twitter"

    # Маппинг Twitter-аккаунтов к ID заданий
    TWITTER_QUESTS_MAP = {
        "Follow": {
            "StoryChain_ai": "4cebe3ff-4dae-4858-9323-8b669d80e45c",
            "tokentails": "cf5a23b1-d48c-4ab9-a74c-785394158224",
            "PanenkaFC90": "040ead29-7436-4457-b7cd-8bd2a8855a49",
            "ScorePlay_xyz": "5f03c7d8-8ee0-443f-a0ad-8fda68dfecd8",
            "wideworlds_ai": "42936f26-3ec6-401f-8ed0-62af343f1fc4",
            "pets_ww": "242ab4dc-2df4-4b97-bcd7-b013ff6635a1",
            "chronicle_ww": "e47be0b8-eedc-445e-a53e-b2f05daabe3c",
            "PictographsNFT": "4e467350-a49b-4413-8fce-4d424d3303bb",
            "entertainm_io": "beb6df6d-b225-46e5-8a4f-20ad967fb4a8",
            "bleetz_io": "01bc9433-359f-4403-9bc8-4295d47dc3c8",
            "RewardedTV_": "87c040a3-060a-4000-b271-051603417e8b",
            "Fantasy_cristal": "17681189-fd69-4aa3-b533-8f452c1bab0c",
            "belgranofantasy": "1cdb82f7-7878-46fc-baec-b75d6e414a25",
            "awanalab": "1a81cbe5-a792-4921-baa0-0c36165e0d7c",
            "arcoin_official": "b852ec9b-7af5-4f07-a677-1bc630bf4579",
            "TheMetakraft": "39b41034-ce80-4057-8cca-e95992182f04",
            "summitx_finance": "12b177a5-aa4e-47c6-aaa9-b14bf9481d0a",
            "thepixudi": "009c0d38-dc3c-4d37-b558-38ece673724a",
            "clustersxyz": "c7d0e2c8-87e7-46df-81f3-48f311735c22",
            "JukebloxDapp": "02e3d5b3-e65e-41c8-b159-405f48255cdf",
            "campnetworkxyz": "2660f24a-e3ac-4093-8c16-7ae718c00731",
        }
    }

    def __init__(self, user: User, auth_client, twitter_auth_token: str, twitter_username: str | None = None, 
                 twitter_password: str | None = None, totp_secret: str | None = None):
        """
        Инициализация Twitter клиента
        
        Args:
            user: Объект пользователя
            auth_client: Авторизованный клиент для CampNetwork
            twitter_auth_token: Токен авторизации Twitter
            twitter_username: Имя пользователя Twitter (без @)
            twitter_password: Пароль от аккаунта Twitter
            totp_secret: Секрет TOTP (если включена 2FA)
        """
        super().__init__(user=user)
        
        # Сохраняем auth_client для использования в запросах к CampNetwork
        self.auth_client = auth_client
        
        # Создаем аккаунт Twitter
        self.twitter_account = twitter.Account(
            auth_token=twitter_auth_token,
            username=twitter_username,
            password=twitter_password,
            totp_secret=totp_secret
        )
        
        # Настройки для клиента Twitter
        self.client_config = {
            "wait_on_rate_limit": True,
            "auto_relogin": True,
            "update_account_info_on_startup": True,
            "capsolver_api_key": CAPMONSTER_API_KEY,
        }
        
        # Добавляем прокси, если оно указано
        if user.proxy:
            self.client_config["proxy"] = user.proxy
            
        # Инициализируем клиент как None
        self.twitter_client = None
        self.is_connected = False
        
        # Добавляем поля для отслеживания ошибок
        self.last_error = None
        self.error_count = 0
        self.settings = Settings()

    
    async def initialize(self) -> bool:
        """
        Инициализирует клиент Twitter
        
        Returns:
            Статус успеха
        """
        try:
            # Создаем клиент Twitter
            self.twitter_client = twitter.Client(self.twitter_account, **self.client_config)
            
            # Устанавливаем соединение
            await self.twitter_client.__aenter__()
            
            # Проверяем статус аккаунта
            await self.twitter_client.establish_status()
            
            if self.twitter_account.status == twitter.AccountStatus.GOOD:
                logger.success(f"{self.user} Twitter клиент инициализирован")
                return True
            else:
                error_msg = f"Проблема со статусом Twitter аккаунта: {self.twitter_account.status}"
                logger.error(f"{self.user} {error_msg}")
                self.last_error = error_msg
                self.error_count += 1
                
                # Если проблема с авторизацией, отмечаем токен как плохой
                if self.twitter_account.status in [twitter.AccountStatus.BAD_TOKEN, twitter.AccountStatus.SUSPENDED]:
                    resource_manager = ResourceManager()
                    await resource_manager.mark_twitter_as_bad(self.user.id)
                    
                    # Если включена автозамена, пробуем заменить токен
                    auto_replace, _ = self.settings.get_resource_settings()
                    if auto_replace:
                        success, message = await resource_manager.replace_twitter(self.user.id)
                        if success:
                            logger.info(f"{self.user} токен Twitter автоматически заменен: {message}")
                            # Пробуем с новым токеном (в другом методе)
                
                return False
                
        except Exception as e:
            error_msg = f"Ошибка при инициализации Twitter клиента: {str(e)}"
            logger.error(f"{self.user} {error_msg}")
            self.last_error = error_msg
            self.error_count += 1
            
            # Проверяем, указывает ли ошибка на проблемы с авторизацией
            if any(x in str(e).lower() for x in ["unauthorized", "authentication", "token", "login", "banned"]):
                resource_manager = ResourceManager()
                await resource_manager.mark_twitter_as_bad(self.user.id)
                
                # Если включена автозамена, пробуем заменить токен
                auto_replace, _ = self.settings.get_resource_settings()
                if auto_replace:
                    success, message = await resource_manager.replace_twitter(self.user.id)
                    if success:
                        logger.info(f"{self.user} токен Twitter автоматически заменен: {message}")
                        # Пробуем с новым токеном (в другом методе)
                
            return False

    async def close(self):
        """Закрывает соединение с Twitter"""
        if self.twitter_client:
            try:
                await self.twitter_client.__aexit__(None, None, None)
                self.twitter_client = None
                logger.info(f"{self.user} Twitter клиент закрыт")
            except Exception as e:
                logger.error(f"{self.user} ошибка при закрытии Twitter клиента: {str(e)}")
    
    async def __aenter__(self):
        """Контекстный менеджер для входа"""
        await self.initialize()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер для выхода"""
        await self.close()
    
    async def connect_twitter_to_camp(self) -> bool:
        """
        Подключает Twitter к CampNetwork с использованием существующего auth_client
        
        Returns:
            Статус успеха
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка подключить Twitter без инициализации клиента")
            return False
            
        try:
            # Проверяем, что у нас есть auth_client и что пользователь авторизован
            if not hasattr(self, 'auth_client') or not self.auth_client.user_id:
                logger.error(f"{self.user} отсутствует auth_client или пользователь не авторизован")
                return False
            
            # Шаг 1: Делаем запрос к /api/twitter/auth для получения параметров авторизации Twitter
            logger.info(f"{self.user} запрашиваю параметры авторизации Twitter")
            
            headers = await self.auth_client.get_headers({
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Referer': 'https://loyalty.campnetwork.xyz/home',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'same-origin',
                'Priority': 'u=0, i',
            })
            
            # Используем auth_client для запроса, но указываем не следовать редиректам
            auth_success, auth_response = await self.auth_client.request(
                url="https://loyalty.campnetwork.xyz/api/twitter/auth",
                method="GET",
                headers=headers,
                allow_redirects=False
            )
            
            # Проверяем, получили ли мы ответ с редиректом
            if 'Location' in auth_response:
                # Извлекаем URL из Location header
                twitter_auth_url = auth_response['Location']
                
                # Парсим URL для извлечения параметров
                import urllib.parse
                parsed_url = urllib.parse.urlparse(twitter_auth_url)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                # Извлекаем необходимые параметры
                state = query_params.get('state', [''])[0]
                code_challenge = query_params.get('code_challenge', [''])[0]
                client_id = query_params.get('client_id', ['TVBRYlFuNzg5RVo4QU11b3EzVV86MTpjaQ'])[0]
                redirect_uri = query_params.get('redirect_uri', ['https://snag-render.com/api/twitter/auth/callback'])[0]
                
                if not state or not code_challenge:
                    logger.error(f"{self.user} не удалось извлечь параметры из URL авторизации")
                    return False
                
                # Шаг 2: Используем параметры для OAuth2 авторизации Twitter
                oauth2_data = {
                    'response_type': 'code',
                    'client_id': client_id,
                    'redirect_uri': redirect_uri,
                    'scope': 'users.read tweet.read',
                    'state': state,
                    'code_challenge': code_challenge,
                    'code_challenge_method': 'plain'
                }
                
                # Выполняем OAuth2 авторизацию
                auth_code = await self.twitter_client.oauth2(**oauth2_data)
                
                if not auth_code:
                    logger.error(f"{self.user} не удалось получить код авторизации от Twitter")
                    return False
                
                # Шаг 3: Делаем запрос на callback URL
                callback_url = f"{redirect_uri}?state={state}&code={auth_code}"
                
                callback_headers = {
                    'User-Agent': ACTUAL_UA,
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Referer': 'https://x.com/',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'cross-site',
                }
                
                # Используем метод запроса из BaseHttpClient
                callback_success, callback_response = await self.auth_client.request(
                    url=callback_url,
                    method="GET",
                    headers=callback_headers,
                    allow_redirects=False,
                )
                
                # Проверяем, получили ли мы редирект на connect URL
                if not callback_success and isinstance(callback_response, dict) and 'Location' in callback_response:
                    connect_url = callback_response['Location']
                    
                    # Шаг 4: Выполняем запрос на подключение Twitter
                    connect_headers = await self.auth_client.get_headers({
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Referer': 'https://x.com/',
                        'DNT': '1',
                        'Sec-GPC': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'cross-site',
                        'Sec-Fetch-User': '?1',
                        'Priority': 'u=0, i',
                    })
                    
                    # Используем auth_client.request для запроса
                    connect_success, connect_response = await self.auth_client.request(
                        url=connect_url,
                        method="GET",
                        headers=connect_headers,
                        allow_redirects=False
                    )
                    
                    # Проверяем результат подключения
                    if connect_success:
                        logger.success(f"{self.user} Twitter подключен")
                        self.is_connected = True
                        return True
                    else:
                        # Проверяем, получили ли мы редирект на основную страницу
                        if isinstance(connect_response, dict) and 'Location' in connect_response and 'loyalty.campnetwork.xyz/loyalty' in connect_response['Location']:
                            logger.success(f"{self.user} Twitter подключен (через редирект)")
                            self.is_connected = True
                            return True
                        
                        logger.success(f"{self.user} Twitter подключен")
                        self.is_connected = True
                        return True
                else:
                    logger.error(f"{self.user} не получен ожидаемый редирект от callback URL")
                    return False
            else:
                logger.error(f"{self.user} не удалось получить редирект на авторизацию Twitter")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при подключении Twitter: {str(e)}")
            return False

    async def disconnect_twitter(self) -> bool:
        """
        Отвязывает Twitter аккаунт от CampNetwork
        
        Returns:
            Статус успеха
        """
        try:
            # Проверяем, подключен ли Twitter к аккаунту
            is_connected = await self.check_twitter_connection_status()
            if not is_connected:
                logger.info(f"{self.user} Twitter уже отключен")
                return True
                
            # Отправляем запрос на отключение Twitter
            headers = await self.auth_client.get_headers({
                'Accept': 'application/json, text/plain, */*',
                'Origin': 'https://loyalty.campnetwork.xyz',
                'Referer': 'https://loyalty.campnetwork.xyz/loyalty?editProfile=1&modalTab=social',
                'Content-Length': '0',
            })
            
            success, response = await self.auth_client.request(
                url="https://loyalty.campnetwork.xyz/api/twitter/auth/disconnect",
                method="POST",
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} Twitter успешно отключен")
                self.is_connected = False
                return True
            else:
                logger.error(f"{self.user} не удалось отключить Twitter: {response}")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при отключении Twitter: {str(e)}")
            return False

    async def replace_twitter_token(self, new_token: str) -> bool:
        """
        Заменяет токен Twitter, отвязывая старый аккаунт и подключая новый
        
        Args:
            new_token: Новый токен авторизации Twitter
            
        Returns:
            Статус успеха
        """
        try:
            # Шаг 1: Отвязываем текущий Twitter аккаунт
            disconnect_success = await self.disconnect_twitter()
            if not disconnect_success:
                logger.warning(f"{self.user} не удалось отвязать текущий Twitter аккаунт")
                # Продолжаем, даже если отвязать не удалось
            
            # Шаг 2: Проверяем, что Twitter действительно отвязан
            is_connected = await self.check_twitter_connection_status()
            
            # Если всё ещё подключен после попытки отвязать, делаем еще одну попытку
            if is_connected:
                logger.warning(f"{self.user} Twitter всё ещё подключен после попытки отключения, пробуем ещё раз")
                await asyncio.sleep(2)  # Небольшая задержка
                await self.disconnect_twitter()
                
                # Проверяем еще раз
                is_connected = await self.check_twitter_connection_status()
                
                if is_connected:
                    logger.error(f"{self.user} не удалось отвязать Twitter аккаунт после повторной попытки")
                    return False
            
            # Шаг 3: Обновляем токен и пересоздаем клиент
            # Закрываем текущий клиент, если он есть
            if self.twitter_client:
                await self.close()
            
            # Обновляем токен
            self.twitter_account.auth_token = new_token
            
            # Инициализируем клиент с новым токеном
            init_success = await self.initialize()
            if not init_success:
                logger.error(f"{self.user} не удалось инициализировать Twitter клиент с новым токеном")
                return False
            
            # Шаг 4: Подключаем Twitter к CampNetwork
            connect_success = await self.connect_twitter_to_camp()
            if not connect_success:
                logger.error(f"{self.user} не удалось подключить Twitter с новым токеном")
                return False
            
            logger.success(f"{self.user} успешно заменен токен Twitter и подключен новый аккаунт")
            return True
            
        except Exception as e:
            logger.error(f"{self.user} ошибка при замене токена Twitter: {str(e)}")
            return False

    async def check_twitter_connection_status(self) -> bool:
        """
        Проверяет, подключен ли Twitter к аккаунту CampNetwork
        
        Returns:
            True если Twitter подключен, False в противном случае
        """
        try:
            # Формируем URL с параметрами
            url = f"{self.BASE_URL}/api/users"
            params = {
                "walletAddress": self.user.public_key,
                "includeDelegation": "false",
                "websiteId": "32afc5c9-f0fb-4938-9572-775dee0b4a2b",
                "organizationId": "26a1764f-5637-425e-89fa-2f3fb86e758c"
            }
            
            headers = await self.auth_client.get_headers({
                'Accept': 'application/json, text/plain, */*',
                'Referer': 'https://loyalty.campnetwork.xyz/loyalty',
            })
            
            # Отправляем запрос
            success, response = await self.auth_client.request(
                url=url,
                method="GET",
                params=params,
                headers=headers
            )
            
            if success and isinstance(response, dict) and "data" in response:
                # Проверяем наличие Twitter-аккаунта в данных пользователя
                user_data = response.get("data", [])[0] if response.get("data") else None
                
                if user_data and "userMetadata" in user_data:
                    user_metadata = user_data["userMetadata"][0] if user_data["userMetadata"] else None
                    
                    if user_metadata:
                        twitter_user = user_metadata.get("twitterUser")
                        twitter_verified_at = user_metadata.get("twitterVerifiedAt")
                        
                        if twitter_user and twitter_verified_at:
                            logger.success(f"{self.user} Twitter уже подключен (@{twitter_user})")
                            self.is_connected = True
                            return True
            
            logger.info(f"{self.user} Twitter не подключен")
            self.is_connected = False
            return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при проверке статуса Twitter: {str(e)}")
            self.is_connected = False
            return False
    
    

    async def follow_account(self, account_name: str) -> Tuple[bool, Optional[str], bool]:
        """
        Подписывается на указанный аккаунт в Twitter
        
        Args:
            account_name: Имя аккаунта для подписки (с @ или без)
            
        Returns:
            Tuple[success, error_message, already_following]: 
            - Статус успеха
            - Сообщение об ошибке (если есть)
            - Флаг, который указывает, были ли мы уже подписаны
        """
        already_following = False
        
        if not self.twitter_client:
            logger.error(f"{self.user} попытка выполнить действие без инициализации клиента")
            return False, "Клиент Twitter не инициализирован", False
            
        try:
            # Убираем @ из имени аккаунта, если он есть
            clean_account_name = remove_at_sign(account_name)
            
            # Получаем пользователя по имени
            user = await self.twitter_client.request_user_by_username(clean_account_name)
            
            if not user:
                logger.error(f"{self.user} не удалось найти пользователя @{clean_account_name}")
                return False, f"Пользователь @{clean_account_name} не найден", False
                
            # Проверяем, подписаны ли мы уже на этого пользователя
            is_following = await self._check_if_following(user.id)
            if is_following:
                logger.info(f"{self.user} уже подписан на @{clean_account_name}")
                return True, None, True  # Возвращаем флаг already_following=True
                
            # Подписываемся на пользователя
            try:
                is_followed = await self.twitter_client.follow(user.id)
                
                if is_followed:
                    logger.success(f"{self.user} подписался на @{clean_account_name}")
                    return True, None, False
                else:
                    logger.warning(f"{self.user} не удалось подписаться на @{clean_account_name}")
                    return False, "Ошибка подписки", False
            except Exception as e:
                error_msg = str(e)
                
                    
                # Код 161 - достигнут лимит подписок
                if "unable to follow more people" in error_msg.lower():
                    logger.warning(f"{self.user} достигнут лимит подписок в Twitter. Попробуйте завтра.")
                    return False, "Достигнут лимит подписок. Попробуйте завтра.", False
                
                # Код 344 - достигнут дневной лимит действий
                elif "daily limit" in error_msg.lower():
                    logger.warning(f"{self.user} достигнут дневной лимит действий в Twitter. Попробуйте завтра.")
                    return False, "Достигнут дневной лимит действий. Попробуйте завтра.", False
                
                logger.error(f"{self.user} ошибка при подписке на @{clean_account_name}: {error_msg}")
                return False, error_msg, False
                    
        except Exception as e:
            error_msg = str(e)
            logger.error(f"{self.user} ошибка при подписке на @{account_name}: {error_msg}")
            return False, error_msg, False

    async def _check_if_following(self, user_id: int) -> bool:
        """
        Проверяет, подписан ли текущий пользователь на указанного пользователя
        
        Args:
            user_id: ID пользователя для проверки
            
        Returns:
            True если уже подписан, False в противном случае
        """
        try:
            # Получаем ID текущего пользователя Twitter
            
            try:
                following = await self.twitter_client.request_followings()
                if following:
                    for followed_user in following:
                        if str(followed_user.id) == str(user_id):
                            return True
            except Exception as e:
                # Если этот метод не сработал, полагаемся на результат friendship
                logger.warning(f"{self.user} не удалось получить список подписок: {str(e)}")
                
            return False
        except Exception as e:
            logger.error(f"{self.user} ошибка при проверке подписки: {str(e)}")
            return False

    async def post_tweet(self, text: str) -> Optional[Any]:
        """
        Публикует твит с указанным текстом
        
        Args:
            text: Текст твита
            
        Returns:
            Объект твита в случае успеха, None в случае ошибки
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка выполнить действие без инициализации клиента")
            return None
            
        try:
            # Публикуем твит
            tweet = await self.twitter_client.tweet(text)
            
            if tweet:
                logger.success(f"{self.user} опубликован твит (ID: {tweet.id})")
                return tweet
            else:
                logger.warning(f"{self.user} не удалось опубликовать твит")
                return None
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при публикации твита: {str(e)}")
            return None
    
    async def retweet(self, tweet_id: int) -> bool:
        """
        Ретвитит указанный твит
        
        Args:
            tweet_id: ID твита для ретвита
            
        Returns:
            Статус успеха
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка выполнить действие без инициализации клиента")
            return False
            
        try:
            # Делаем ретвит
            retweet_id = await self.twitter_client.repost(tweet_id)
            
            if retweet_id:
                logger.success(f"{self.user} ретвит выполнен")
                return True
            else:
                logger.warning(f"{self.user} не удалось сделать ретвит")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при ретвите: {str(e)}")
            return False
    
    async def like_tweet(self, tweet_id: int) -> bool:
        """
        Ставит лайк указанному твиту
        
        Args:
            tweet_id: ID твита для лайка
            
        Returns:
            Статус успеха
        """
        if not self.twitter_client:
            logger.error(f"{self.user} попытка выполнить действие без инициализации клиента")
            return False
            
        try:
            # Ставим лайк
            is_liked = await self.twitter_client.like(tweet_id)
            
            if is_liked:
                logger.success(f"{self.user} лайк выполнен")
                return True
            else:
                logger.warning(f"{self.user} не удалось поставить лайк")
                return False
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при лайке: {str(e)}")
            return False
    
    async def complete_follow_quest(self, account_name: str) -> bool:
        """
        Выполняет задание подписки на аккаунт и отмечает его как выполненное в CampNetwork
        
        Args:
            account_name: Имя аккаунта для подписки
            
        Returns:
            Статус успеха
        """
        # Получаем ID задания для этого аккаунта
        quest_id = self.TWITTER_QUESTS_MAP.get("Follow", {}).get(account_name)
        if not quest_id:
            logger.warning(f"{self.user} нет ID задания для подписки на {account_name}")
            return False
        
        # Проверяем, выполнено ли уже задание
        try:
            async with Session() as session:
                db = DB(session=session)
                if await db.is_quest_completed(self.user.id, quest_id):
                    logger.info(f"{self.user} задание подписки на {account_name} уже выполнено")
                    return True
        except Exception as e:
            logger.error(f"{self.user} ошибка при проверке задания: {str(e)}")
        
        # Выполняем подписку
        follow_success, error_message = await self.follow_account(account_name)
        
        # Если подписаться не удалось, но это из-за лимитов Twitter - логируем информацию
        if not follow_success:
            if error_message and ("лимит подписок" in error_message or "дневной лимит" in error_message):
                logger.warning(f"{self.user} {error_message} Пропускаем задание подписки на {account_name}")
                return False
            else:
                logger.error(f"{self.user} не удалось подписаться на {account_name}")
                return False
        
        # Отправляем запрос на выполнение задания
        try:
            complete_url = f"{self.BASE_URL}/api/loyalty/rules/{quest_id}/complete"
            
            headers = await self.auth_client.get_headers({
                'Accept': 'application/json, text/plain, */*',
                'Content-Type': 'application/json',
                'Origin': 'https://loyalty.campnetwork.xyz',
                'DNT': '1',
                'Sec-GPC': '1',
                'Priority': 'u=0',
            })
            
            success, response = await self.auth_client.request(
                url=complete_url,
                method="POST",
                json_data={},
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} успешно выполнено задание подписки на {account_name}")
                
                # Отмечаем задание как выполненное в БД
                try:
                    async with Session() as session:
                        db = DB(session=session)
                        await db.mark_quest_completed(self.user.id, quest_id)
                except Exception as e:
                    logger.error(f"{self.user} ошибка сохранения статуса: {e}")
                
                return True
            else:
                # Проверка на "You have already been rewarded"
                if isinstance(response, dict) and response.get("message") == "You have already been rewarded" and response.get("rewarded") is True:
                    logger.info(f"{self.user} задание подписки на {account_name} уже выполнено ранее")
                    
                    # Отмечаем задание как выполненное в БД
                    try:
                        async with Session() as session:
                            db = DB(session=session)
                            await db.mark_quest_completed(self.user.id, quest_id)
                    except Exception as e:
                        logger.error(f"{self.user} ошибка сохранения статуса: {e}")
                    
                    return True
                else:
                    logger.error(f"{self.user} ошибка выполнения задания подписки на {account_name}")
                    return False
        except Exception as e:
            logger.error(f"{self.user} ошибка при отправке запроса: {str(e)}")
            return False

    async def complete_follow_quests(self, account_names: List[str]) -> Dict[str, bool]:
        """
        Выполняет задания подписки на несколько аккаунтов
        
        Args:
            account_names: Список аккаунтов для подписки
            
        Returns:
            Словарь с результатами {аккаунт: успех}
        """
        settings = Settings()
        action_min_delay, action_max_delay = settings.get_twitter_action_delay()
        quest_min_delay, quest_max_delay = settings.get_twitter_quest_delay()
        
        results = {}
        
        # Перемешиваем аккаунты для случайного порядка
        random_accounts = account_names.copy()
        random.shuffle(random_accounts)
        
        for account in random_accounts:
            # Выполняем задание подписки
            success = await self.complete_follow_quest(account)
            results[account] = success
            
            # Задержка между заданиями
            if account != random_accounts[-1]:  # Если это не последний аккаунт
                delay = random.uniform(quest_min_delay, quest_max_delay)
                logger.info(f"{self.user} задержка {int(delay)} сек. перед следующей подпиской")
                await asyncio.sleep(delay)
        
        return results

    async def complete_twitter_quests(self, follow_accounts: List[str] | None = None,
                                     tweet_text: str | None = None,
                                     tweet_id_to_like: int | None = None,
                                     tweet_id_to_retweet: int | None = None) -> bool:
        """
        Выполняет Twitter задания с улучшенной обработкой ошибок
        
        Returns:
            Статус успеха
        """
        min_delay, max_delay = self.settings.get_twitter_quest_delay()
        auto_replace, max_failures = self.settings.get_resource_settings()
        
        success_count = 0
        total_tasks = 0
        
        # Для отслеживания ограничений Twitter
        twitter_rate_limited = False
        rate_limit_message = ""
        
        try:
            # Инициализируем клиент
            if not await self.initialize():
                # Если инициализация не удалась и у нас есть последняя ошибка, проверяем,
                # можно ли заменить токен автоматически
                if self.last_error and auto_replace:
                    resource_manager = ResourceManager()
                    success, message = await resource_manager.replace_twitter(self.user.id)
                    
                    if success:
                        logger.info(f"{self.user} токен Twitter заменен автоматически: {message}")
                        # Получаем новый токен и пробуем заново
                        async with Session() as session:
                            updated_wallet = await session.get(User, self.user.id)
                            if updated_wallet and updated_wallet.twitter_token:
                                # Отвязываем текущий аккаунт Twitter и подключаем новый
                                await self.disconnect_twitter()
                                # Обновляем токен в текущем экземпляре
                                self.twitter_account.auth_token = updated_wallet.twitter_token
                                # Пробуем снова инициализировать
                                if await self.initialize():
                                    # Подключаем Twitter к CampNetwork
                                    connect_success = await self.connect_twitter_to_camp()
                                    if connect_success:
                                        logger.success(f"{self.user} успешная реинициализация с новым токеном Twitter")
                                    else:
                                        logger.error(f"{self.user} не удалось подключить Twitter с новым токеном")
                                        return False
                                else:
                                    logger.error(f"{self.user} не удалось инициализировать с новым токеном Twitter")
                                    return False
                            else:
                                return False
                    else:
                        logger.error(f"{self.user} не удалось заменить токен Twitter: {message}")
                        return False
                else:
                    logger.error(f"{self.user} не удалось инициализировать Twitter клиент")
                    return False
            
            # Выполняем задания в случайном порядке
            task_types = []
            
            # Формируем список заданий для выполнения
            if follow_accounts:
                task_types.append("follow")
                total_tasks += 1
            
            if tweet_text:
                task_types.append("tweet")
                total_tasks += 1
            
            if tweet_id_to_like:
                task_types.append("like")
                total_tasks += 1
            
            if tweet_id_to_retweet:
                task_types.append("retweet")
                total_tasks += 1
            
            # Перемешиваем типы заданий для случайного порядка выполнения
            random.shuffle(task_types)
            
            # Выполняем задания
            for i, task_type in enumerate(task_types):
                try:
                    # Если уже достигнут лимит Twitter, пропускаем оставшиеся задания
                    if twitter_rate_limited:
                        logger.warning(f"{self.user} пропускаем задание {task_type} из-за ограничений Twitter: {rate_limit_message}")
                        continue
                    
                    if task_type == "follow" and follow_accounts:
                        # Выполняем подписки
                        follow_results = {}
                        for account in follow_accounts:
                            follow_success, error_message = await self.follow_account(account)
                            follow_results[account] = follow_success
                            
                            # Проверяем, не достигнут ли лимит подписок
                            if not follow_success and error_message and (
                                "лимит подписок" in error_message or 
                                "дневной лимит" in error_message
                            ):
                                twitter_rate_limited = True
                                rate_limit_message = error_message
                                logger.warning(f"{self.user} {error_message} Пропускаем оставшиеся подписки")
                                break
                                
                            # Добавляем задержку между подписками
                            if len(follow_accounts) > 1 and account != follow_accounts[-1]:
                                await asyncio.sleep(random.uniform(min_delay/2, max_delay/2))
                        
                        if any(follow_results.values()):
                            success_count += 1
                    
                    elif task_type == "tweet" and tweet_text:
                        # Добавляем уникальный хэштег для избежания дубликатов
                        unique_text = f"{tweet_text} #{random.randint(10000, 99999)}"
                        tweet = await self.post_tweet(unique_text)
                        if tweet:
                            success_count += 1
                    
                    elif task_type == "like" and tweet_id_to_like:
                        if await self.like_tweet(tweet_id_to_like):
                            success_count += 1
                    
                    elif task_type == "retweet" and tweet_id_to_retweet:
                        if await self.retweet(tweet_id_to_retweet):
                            success_count += 1
                
                except Exception as e:
                    error_msg = f"Ошибка при выполнении {task_type} задания: {str(e)}"
                    logger.error(f"{self.user} {error_msg}")
                    self.last_error = error_msg
                    self.error_count += 1
                    
                    # Проверяем на ограничения Twitter
                    if "limit" in str(e).lower() or "unable to follow" in str(e).lower():
                        twitter_rate_limited = True
                        rate_limit_message = f"Достигнут лимит Twitter в задании {task_type}"
                        logger.warning(f"{self.user} {rate_limit_message}")
                    
                    # Проверяем, указывает ли ошибка на проблемы с авторизацией или прокси
                    if any(x in str(e).lower() for x in ["unauthorized", "authentication", "token", "login", "banned"]):
                        resource_manager = ResourceManager()
                        await resource_manager.mark_twitter_as_bad(self.user.id)
                    
                    if "proxy" in str(e).lower() or "connection" in str(e).lower() or "timeout" in str(e).lower():
                        resource_manager = ResourceManager()
                        
                        # Если достигнут порог ошибок, отмечаем прокси как плохое
                        if self.error_count >= max_failures:
                            await resource_manager.mark_proxy_as_bad(self.user.id)
                
                # Добавляем задержку между заданиями, если это не последнее задание
                if i < len(task_types) - 1 and not twitter_rate_limited:
                    delay = random.uniform(min_delay, max_delay)
                    logger.info(f"{self.user} задержка {int(delay)} сек. перед следующим Twitter заданием")
                    await asyncio.sleep(delay)
            
            # Закрываем клиент Twitter
            await self.close()
            
            # Если были достигнуты лимиты Twitter, выводим информативное сообщение
            if twitter_rate_limited:
                logger.warning(f"{self.user} некоторые Twitter задания не выполнены из-за ограничений: {rate_limit_message}. Попробуйте завтра.")
                
                # Если хотя бы одно задание было выполнено, то считаем успехом
                if success_count > 0:
                    logger.success(f"{self.user} частично выполнены Twitter задания: {success_count} из {total_tasks}")
                    return True
                else:
                    logger.warning(f"{self.user} не удалось выполнить ни одного Twitter задания из-за ограничений")
                    return False
            
            # Возвращаем успех, если хотя бы одно задание выполнено
            success = success_count > 0
            if success:
                logger.success(f"{self.user} успешно выполнено {success_count} из {total_tasks} Twitter заданий")
            else:
                logger.warning(f"{self.user} не удалось выполнить ни одного Twitter задания")
                
            return success
            
        except Exception as e:
            # Закрываем клиент Twitter в случае ошибки
            await self.close()
            error_msg = f"ошибка при выполнении Twitter заданий: {str(e)}"
            logger.error(f"{self.user} {error_msg}")
            self.last_error = error_msg
            self.error_count += 1
            
            # Проверяем, может быть проблема с прокси
            if "proxy" in str(e).lower() or "connection" in str(e).lower() or "timeout" in str(e).lower():
                resource_manager = ResourceManager()
                
                # Если достигнут порог ошибок, отмечаем прокси как плохое
                if self.error_count >= max_failures:
                    await resource_manager.mark_proxy_as_bad(self.user.id)
            
            # Проверяем, может быть проблема с токеном Twitter
            if any(x in str(e).lower() for x in ["unauthorized", "authentication", "token", "login", "banned"]):
                resource_manager = ResourceManager()
                await resource_manager.mark_twitter_as_bad(self.user.id)
                
            return False
