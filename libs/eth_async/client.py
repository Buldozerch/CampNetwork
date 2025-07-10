import random
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple, Union, Callable

import requests
from web3 import AsyncWeb3
from web3.eth import AsyncEth
from fake_useragent import UserAgent
from eth_account.signers.local import LocalAccount

from . import exceptions
from .wallet import Wallet
from .contracts import Contracts
from .transactions import Transactions
from .data.models import Networks, Network
from .logger import EthLogger


class Client:
    """
    Клиент для взаимодействия с Ethereum сетью через web3.py.
    
    Attributes:
        network (Network): Сеть Ethereum для подключения
        account (LocalAccount): Аккаунт для подписи транзакций
        w3 (AsyncWeb3): Инстанс AsyncWeb3
        wallet (Wallet): Методы для работы с кошельком
        contracts (Contracts): Методы для работы с контрактами
        transactions (Transactions): Методы для работы с транзакциями
    """
    network: Network
    account: LocalAccount 
    w3: AsyncWeb3

    def __init__(
            self,
            private_key: str | None = None,
            network: Network = Networks.Goerli,
            proxy: str | None = None,
            check_proxy: bool = False,
            logger_level=logging.ERROR
    ) -> None:
        """
        Инициализирует клиента eth_async.
        
        Args:
            private_key: Приватный ключ для подписи транзакций (опционально)
            network: Сеть Ethereum для подключения
            proxy: Прокси для запросов (опционально)
            check_proxy: Проверять ли работоспособность прокси
            logger_level: Уровень логирования
        """
        self.network = network
        self.headers = {
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/json',
            'user-agent': UserAgent().chrome
        }
        self.proxy = proxy
        if self.proxy:
            if 'http' not in self.proxy:
                self.proxy = f'http://{self.proxy}'

            if check_proxy:
                your_ip = requests.get(
                    'http://eth0.me/', proxies={'http': self.proxy, 'https': self.proxy}, timeout=10
                ).text.rstrip()

        # Инициализация логгера
        self.logger = EthLogger(level=logger_level)

        # Инициализация AsyncWeb3
        self.w3 = AsyncWeb3(
            provider=AsyncWeb3.AsyncHTTPProvider(
                endpoint_uri=self.network.rpc,
                request_kwargs={'proxy': self.proxy, 'headers': self.headers},
            ),
            modules={'eth': (AsyncEth,)},
            middleware=[]
        )

        # Загрузка аккаунта
        if private_key:
            self.account = self.w3.eth.account.from_key(private_key=private_key)
        else:
            self.account = self.w3.eth.account.create(extra_entropy=str(random.randint(1, 999_999_999)))

        # Инициализация модулей
        self.wallet = Wallet(self)
        self.contracts = Contracts(self)
        self.transactions = Transactions(self)
        
        # Логируем инициализацию
        self.logger.info(f"Client initialized for network: {self.network.name}")


    async def is_connected(self) -> bool:
        """
        Проверяет соединение с нодой.
        
        Returns:
            bool: True если соединение установлено
        """
        return await self.w3.is_connected()
        
    async def batch_request(self, calls: List[Tuple]) -> List[Any]:
        """
        Выполняет пакетный запрос для нескольких вызовов.
        
        Args:
            calls: Список кортежей (функция, аргументы)
        
        Returns:
            List[Any]: Результаты запросов в том же порядке
        """
        self.logger.debug(f"Executing batch request with {len(calls)} calls")
        
        async with self.w3.batch_requests() as batch:
            futures = []
            for func, args in calls:
                if isinstance(args, dict):
                    futures.append(func(**args))
                elif isinstance(args, (list, tuple)):
                    futures.append(func(*args))
                elif args is None:
                    futures.append(func())
                else:
                    futures.append(func(args))
            
            results = await asyncio.gather(*futures)
            
        self.logger.debug(f"Batch request completed")
        return results
        
    async def close(self):
        """
        Закрывает все соединения и очищает ресурсы.
        """
        if hasattr(self.w3.provider, 'disconnect'):
            await self.w3.provider.disconnect()
        
        self.logger.info("Client connections closed")
