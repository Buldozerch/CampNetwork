from __future__ import annotations
from typing import Optional, Dict, Any, List, Callable, Awaitable, Union, Tuple
import asyncio
import logging

from web3 import AsyncWeb3

from .client import Client
from .data.models import Networks
from .exceptions import Web3AsyncException

logger = logging.getLogger(__name__)


class WSClient(Client):
    """
    Расширенный клиент с поддержкой WebSocket.
    """
    
    def __init__(
        self, 
        ws_endpoint: str, 
        private_key: Optional[str] = None,
        network = Networks.Ethereum,
        proxy: Optional[str] = None,
        check_proxy: bool = True,
        logger_level = logging.INFO
    ):
        """
        Инициализирует клиент WebSocket.
        
        Args:
            ws_endpoint: URL WebSocket
            private_key: Приватный ключ (опционально)
            network: Сеть Ethereum
            proxy: Прокси (опционально)
            check_proxy: Проверять ли работоспособность прокси
            logger_level: Уровень логирования
        """
        super().__init__(
            private_key=private_key,
            network=network,
            proxy=proxy,
            check_proxy=check_proxy,
            logger_level=logger_level
        )
        
        self.ws_endpoint = ws_endpoint
        self.ws_client = None
        self.subscriptions = {}
        
    async def connect_ws(self) -> AsyncWeb3:
        """
        Подключается к WebSocket.
        
        Returns:
            AsyncWeb3: Инстанс AsyncWeb3 для работы с WebSocket
        """
        if self.ws_client and await self.ws_client.is_connected():
            return self.ws_client
            
        self.logger.info(f"Connecting to WebSocket: {self.ws_endpoint}")
        self.ws_client = AsyncWeb3(AsyncWeb3.WebSocketProvider(self.ws_endpoint))
        
        # Проверяем подключение
        if not await self.ws_client.is_connected():
            self.logger.error(f"Failed to connect to WebSocket: {self.ws_endpoint}")
            raise Web3AsyncException(f"Failed to connect to WebSocket: {self.ws_endpoint}")
            
        self.logger.info(f"Successfully connected to WebSocket")
        return self.ws_client
        
    async def close_ws(self) -> None:
        """
        Закрывает WebSocket соединение.
        """
        if self.ws_client:
            self.logger.info("Closing WebSocket connection")
            await self.unsubscribe_all()
            if hasattr(self.ws_client.provider, 'disconnect'):
                self.ws_client.provider.disconnect()
            self.ws_client = None
            
    async def __aenter__(self) -> 'WSClient':
        """
        Вход в контекстный менеджер.
        """
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Выход из контекстного менеджера.
        """
        await self.close_ws()
    
    async def subscribe_new_blocks(self, callback: Callable[[Dict[str, Any]], Awaitable[bool]]) -> str:
        """
        Подписывается на новые блоки.
        
        Args:
            callback: Функция обработки новых блоков, возвращает True для продолжения подписки
            
        Returns:
            str: ID подписки
        """
        ws = await self.connect_ws()
        
        self.logger.info("Subscribing to new blocks")
        subscription_id = await ws.eth.subscribe('newHeads')
        
        self.subscriptions[subscription_id] = {
            'type': 'newHeads',
            'callback': callback
        }
        
        # Запускаем обработку сообщений
        asyncio.create_task(self._process_subscription(subscription_id))
        
        return subscription_id
        
    async def subscribe_logs(
        self, 
        address: Optional[Union[str, List[str]]] = None, 
        topics: Optional[List[str]] = None,
        callback: Optional[Callable[[Dict[str, Any]], Awaitable[bool]]] = None
    ) -> str:
        """
        Подписывается на события логов.
        
        Args:
            address: Адрес или список адресов для фильтрации (опционально)
            topics: Список топиков для фильтрации (опционально)
            callback: Функция обработки логов, возвращает True для продолжения подписки
            
        Returns:
            str: ID подписки
        """
        ws = await self.connect_ws()
        
        filter_params = {}
        if address:
            filter_params['address'] = address
        if topics:
            filter_params['topics'] = topics
            
        self.logger.info(f"Subscribing to logs with filter: {filter_params}")
        subscription_id = await ws.eth.subscribe('logs', filter_params)
        
        self.subscriptions[subscription_id] = {
            'type': 'logs',
            'callback': callback,
            'filter': filter_params
        }
        
        # Запускаем обработку сообщений
        asyncio.create_task(self._process_subscription(subscription_id))
        
        return subscription_id
        
    async def subscribe_pending_transactions(self, callback: Callable[[str], Awaitable[bool]]) -> str:
        """
        Подписывается на ожидающие транзакции.
        
        Args:
            callback: Функция обработки транзакций, возвращает True для продолжения подписки
            
        Returns:
            str: ID подписки
        """
        ws = await self.connect_ws()
        
        self.logger.info("Subscribing to pending transactions")
        subscription_id = await ws.eth.subscribe('pendingTransactions')
        
        self.subscriptions[subscription_id] = {
            'type': 'pendingTransactions',
            'callback': callback
        }
        
        # Запускаем обработку сообщений
        asyncio.create_task(self._process_subscription(subscription_id))
        
        return subscription_id
        
    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Отписывается от подписки.
        
        Args:
            subscription_id: ID подписки
            
        Returns:
            bool: True, если отписка успешна
        """
        if subscription_id not in self.subscriptions:
            self.logger.warning(f"Subscription {subscription_id} not found")
            return False
            
        ws = await self.connect_ws()
        
        try:
            self.logger.info(f"Unsubscribing from {subscription_id}")
            success = await ws.eth.unsubscribe(subscription_id)
            
            if success:
                del self.subscriptions[subscription_id]
                self.logger.info(f"Successfully unsubscribed from {subscription_id}")
            else:
                self.logger.warning(f"Failed to unsubscribe from {subscription_id}")
                
            return success
        except Exception as e:
            self.logger.error(f"Error unsubscribing from {subscription_id}: {str(e)}")
            return False
            
    async def unsubscribe_all(self) -> None:
        """
        Отписывается от всех подписок.
        """
        subscription_ids = list(self.subscriptions.keys())
        
        for subscription_id in subscription_ids:
            await self.unsubscribe(subscription_id)
            
    async def _process_subscription(self, subscription_id: str) -> None:
        """
        Обрабатывает сообщения подписки.
        
        Args:
            subscription_id: ID подписки
        """
        if subscription_id not in self.subscriptions:
            self.logger.warning(f"Subscription {subscription_id} not found")
            return
            
        subscription = self.subscriptions[subscription_id]
        callback = subscription['callback']
        
        if not callback:
            self.logger.warning(f"No callback for subscription {subscription_id}")
            return
            
        ws = await self.connect_ws()
        
        try:
            self.logger.debug(f"Starting processing subscription {subscription_id}")
            
            async for message in ws.socket.process_subscriptions():
                if message['subscription'] != subscription_id:
                    continue
                    
                try:
                    # Вызываем колбэк, передаем параметр в зависимости от типа подписки
                    if subscription['type'] == 'newHeads':
                        continue_subscription = await callback(message['result'])
                    elif subscription['type'] == 'logs':
                        continue_subscription = await callback(message['result'])
                    elif subscription['type'] == 'pendingTransactions':
                        continue_subscription = await callback(message['result'])
                    else:
                        continue_subscription = await callback(message['result'])
                        
                    # Если колбэк вернул False, отписываемся
                    if not continue_subscription:
                        self.logger.info(f"Callback returned False, unsubscribing from {subscription_id}")
                        await self.unsubscribe(subscription_id)
                        break
                        
                except Exception as e:
                    self.logger.error(f"Error in callback for subscription {subscription_id}: {str(e)}")
                    
        except Exception as e:
            self.logger.error(f"Error processing subscription {subscription_id}: {str(e)}")
