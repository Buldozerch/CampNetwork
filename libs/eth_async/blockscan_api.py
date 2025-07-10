from typing import Dict, Any, List, Optional, Union
from fake_useragent import UserAgent

from .exceptions import APIException
from .utils.web_requests import async_get, aiohttp_params
from .logger import EthLogger

logger = EthLogger()


class Tag:
    """
    Класс с возможными значениями тегов блока.
    """
    Earliest: str = 'earliest'
    Pending: str = 'pending'
    Latest: str = 'latest'
    Safe: str = 'safe'
    Finalized: str = 'finalized'


class Sort:
    """
    Класс с возможными значениями сортировки.
    """
    Asc: str = 'asc'
    Desc: str = 'desc'


class Module:
    """
    Базовый класс для модулей API блокчейн-сканера.

    Attributes:
        key (str): API ключ.
        url (str): URL входной точки API.
        headers (Dict[str, Any]): Заголовки для запросов.
        module (str): Название модуля.
    """
    key: str
    url: str
    headers: Dict[str, Any]
    module: str

    def __init__(self, key: str, url: str, headers: Dict[str, Any]) -> None:
        """
        Инициализирует класс.

        Args:
            key (str): API ключ.
            url (str): URL входной точки API.
            headers (Dict[str, Any]): Заголовки для запросов.
        """
        self.key = key
        self.url = url
        self.headers = headers
        self.logger = logger


class Account(Module):
    """
    Класс для работы с модулем 'account' API блокчейн-сканера.
    """
    module: str = 'account'

    async def balance(self, address: str, tag: str = Tag.Latest) -> Dict[str, Any]:
        """
        Возвращает баланс эфира по указанному адресу.

        https://docs.etherscan.io/api-endpoints/accounts#get-ether-balance-for-a-single-address

        Args:
            address (str): Адрес для проверки баланса
            tag (Union[str, Tag]): Параметр блока: "earliest", "pending" или "latest". ("latest")

        Returns:
            Dict[str, Any]: Словарь с балансом эфира адреса в wei.
        """
        action = 'balance'
        if tag not in (Tag.Earliest, Tag.Pending, Tag.Latest, Tag.Safe, Tag.Finalized):
            raise APIException('"tag" parameter have to be either "earliest", "pending", "latest", "safe" or "finalized"')

        params = {
            'module': self.module,
            'action': action,
            'address': address,
            'tag': tag,
            'apikey': self.key,
        }
        self.logger.debug(f"Getting balance for {address} with tag {tag}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)

    async def balancemulti(self, address: List[str], tag: str = Tag.Latest) -> Dict[str, Any]:
        """
        Возвращает баланс эфира по нескольким адресам.
        
        Args:
            address: Список адресов
            tag: Параметр блока
            
        Returns:
            Dict[str, Any]: Словарь с балансами эфира адресов в wei
        """
        action = 'balancemulti'

        if tag not in (Tag.Earliest, Tag.Pending, Tag.Latest, Tag.Safe, Tag.Finalized):
            raise APIException('"tag" parameter have to be either "earliest", "pending", "latest", "safe" or "finalized"')

        params = {
            'module': self.module,
            'action': action,
            'address': ','.join(address),
            'tag': tag,
            'apikey': self.key,
        }
        self.logger.debug(f"Getting balances for {len(address)} addresses with tag {tag}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)

    async def txlist(
            self, address: str, startblock: int | None = None, endblock: int | None = None,
            page: int | None = None, offset: int | None = None, sort: str | Sort = Sort.Asc
    ) -> Dict[str, Any]:
        """
        Возвращает список транзакций, выполненных по адресу, с опциональной пагинацией.

        https://docs.etherscan.io/api-endpoints/accounts#get-a-list-of-normal-transactions-by-address

        Args:
            address (str): Адрес для получения списка транзакций.
            startblock (Optional[int]): Номер блока, с которого начать поиск транзакций.
            endblock (Optional[int]): Номер блока, на котором закончить поиск транзакций.
            page (Optional[int]): Номер страницы, если пагинация включена.
            offset (Optional[int]): Количество транзакций, отображаемых на странице.
            sort (Union[str, Sort]): Параметр сортировки, используйте "asc" для сортировки по возрастанию и "desc" для сортировки
                по убыванию. ("asc")

        Returns:
            Dict[str, Any]: Словарь со списком транзакций, выполненных по адресу.
        """
        action = 'txlist'
        if sort not in ('asc', 'desc'):
            raise APIException('"sort" parameter have to be either "asc" or "desc"')

        params = {
            'module': self.module,
            'action': action,
            'address': address,
            'startblock': startblock,
            'endblock': endblock,
            'page': page,
            'offset': offset,
            'sort': sort,
            'apikey': self.key,
        }

        self.logger.debug(f"Getting transaction list for {address}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)

    async def txlistinternal(
            self,
            address: str,
            startblock: int | None = None,
            endblock: int | None = None,
            page: int = 1,
            offset: int = 0,
            sort: str = Sort.Asc
    ) -> Dict[str, Any]:
        """
        Возвращает список внутренних транзакций, выполненных по адресу.
        
        Args:
            address: Адрес для получения списка транзакций
            startblock: Номер блока, с которого начать поиск
            endblock: Номер блока, на котором закончить поиск
            page: Номер страницы
            offset: Количество транзакций на странице
            sort: Параметр сортировки
            
        Returns:
            Dict[str, Any]: Словарь со списком внутренних транзакций
        """
        action = 'txlistinternal'

        if sort not in ('asc', 'desc'):
            raise APIException('"sort" parameter have to be either "asc" or "desc"')

        params = {
            'module': self.module,
            'action': action,
            'address': address,
            'startblock': startblock,
            'endblock': endblock,
            'page': page,
            'offset': offset,
            'sort': sort,
            'apikey': self.key,
        }

        self.logger.debug(f"Getting internal transaction list for {address}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)

    async def tokentx(
            self,
            contractaddress: str,
            address: str,
            page: int = 1,
            offset: int = 0,
            startblock: int | None = None,
            endblock: int | None = None,
            sort: str = Sort.Asc
    ) -> Dict[str, Any]:
        """
        Возвращает список транзакций ERC-20 токенов по указанному адресу.
        
        Args:
            contractaddress: Адрес контракта токена
            address: Адрес для получения списка транзакций
            page: Номер страницы
            offset: Количество транзакций на странице
            startblock: Номер блока, с которого начать поиск
            endblock: Номер блока, на котором закончить поиск
            sort: Параметр сортировки
            
        Returns:
            Dict[str, Any]: Словарь со списком транзакций токенов
        """
        action = 'tokentx'

        if sort not in ('asc', 'desc'):
            raise APIException('"sort" parameter have to be either "asc" or "desc"')

        params = {
            'module': self.module,
            'action': action,
            'contractaddress': contractaddress,
            'address': address,
            'page': page,
            'offset': offset,
            'startblock': startblock,
            'endblock': endblock,
            'sort': sort,
            'apikey': self.key,
        }

        self.logger.debug(f"Getting token transactions for {address}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)
        
    async def tokennfttx(
            self,
            contractaddress: str = None,
            address: str = None,
            page: int = 1,
            offset: int = 0,
            startblock: int | None = None,
            endblock: int | None = None,
            sort: str = Sort.Asc
    ) -> Dict[str, Any]:
        """
        Возвращает список транзакций ERC-721 (NFT) токенов по указанному адресу.
        
        Args:
            contractaddress: Адрес контракта токена
            address: Адрес для получения списка транзакций
            page: Номер страницы
            offset: Количество транзакций на странице
            startblock: Номер блока, с которого начать поиск
            endblock: Номер блока, на котором закончить поиск
            sort: Параметр сортировки
            
        Returns:
            Dict[str, Any]: Словарь со списком транзакций NFT токенов
        """
        action = 'tokennfttx'

        if sort not in ('asc', 'desc'):
            raise APIException('"sort" parameter have to be either "asc" or "desc"')

        params = {
            'module': self.module,
            'action': action,
            'contractaddress': contractaddress,
            'address': address,
            'page': page,
            'offset': offset,
            'startblock': startblock,
            'endblock': endblock,
            'sort': sort,
            'apikey': self.key,
        }

        self.logger.debug(f"Getting NFT transactions for {address}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)


class Contract(Module):
    """
    Класс для работы с модулем 'contract' API блокчейн-сканера.
    """
    module: str = 'contract'

    async def getabi(self, address: str) -> Dict[str, Any]:
        """
        Возвращает Contract Application Binary Interface (ABI) для верифицированного смарт-контракта.

        https://docs.etherscan.io/api-endpoints/contracts#get-contract-abi-for-verified-contract-source-codes

        Args:
            address (str): Адрес контракта, у которого есть верифицированный исходный код.

        Returns:
            Dict[str, Any]: Словарь с ABI контракта.
        """
        action = 'getabi'
        params = {
            'module': self.module,
            'action': action,
            'address': address,
            'apikey': self.key,
        }
        self.logger.debug(f"Getting ABI for contract {address}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)

    async def getsourcecode(self, address: str) -> Dict[str, Any]:
        """
        Возвращает исходный код смарт-контракта.
        
        Args:
            address: Адрес контракта
            
        Returns:
            Dict[str, Any]: Словарь с исходным кодом контракта
        """
        action = 'getsourcecode'

        params = {
            'module': self.module,
            'action': action,
            'address': address,
            'apikey': self.key,
        }
        self.logger.debug(f"Getting source code for contract {address}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)


class Transaction(Module):
    """
    Класс для работы с модулем 'transaction' API блокчейн-сканера.
    """
    module: str = 'transaction'

    async def getstatus(self, txhash: str) -> Dict[str, Any]:
        """
        Возвращает статус транзакции.
        
        Args:
            txhash: Хеш транзакции
            
        Returns:
            Dict[str, Any]: Словарь со статусом транзакции
        """
        action = 'getstatus'

        params = {
            'module': self.module,
            'action': action,
            'txhash': txhash,
            'apikey': self.key,
        }
        self.logger.debug(f"Getting status for transaction {txhash}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)
        
    async def gettxreceiptstatus(self, txhash: str) -> Dict[str, Any]:
        """
        Возвращает статус чека транзакции.
        
        Args:
            txhash: Хеш транзакции
            
        Returns:
            Dict[str, Any]: Словарь со статусом чека транзакции
        """
        action = 'gettxreceiptstatus'

        params = {
            'module': self.module,
            'action': action,
            'txhash': txhash,
            'apikey': self.key,
        }
        self.logger.debug(f"Getting receipt status for transaction {txhash}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)


class Block(Module):
    """
    Класс для работы с модулем 'block' API блокчейн-сканера.
    """
    module: str = 'block'
    
    async def getblockreward(self, blockno: int) -> Dict[str, Any]:
        """
        Возвращает информацию о вознаграждении за блок.
        
        Args:
            blockno: Номер блока
            
        Returns:
            Dict[str, Any]: Словарь с информацией о вознаграждении
        """
        action = 'getblockreward'
        
        params = {
            'module': self.module,
            'action': action,
            'blockno': blockno,
            'apikey': self.key,
        }
        self.logger.debug(f"Getting block reward for block {blockno}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)


class Logs(Module):
    """
    Класс для работы с модулем 'logs' API блокчейн-сканера.
    """
    module: str = 'logs'
    
    async def getLogs(
        self, 
        address: str = None,
        fromBlock: int = None,
        toBlock: int = None,
        topic0: str = None,
        topic1: str = None,
        topic2: str = None,
        topic3: str = None,
        topic0_1_opr: str = None,
        topic1_2_opr: str = None,
        topic2_3_opr: str = None,
        topic0_2_opr: str = None,
        topic0_3_opr: str = None,
        topic1_3_opr: str = None
    ) -> Dict[str, Any]:
        """
        Получает события логов.
        
        Args:
            address: Адрес контракта
            fromBlock: Начальный блок
            toBlock: Конечный блок
            topic0: Первый топик (signature)
            topic1: Второй топик
            topic2: Третий топик
            topic3: Четвертый топик
            topic0_1_opr: Оператор между topic0 и topic1 ('and'/'or')
            topic1_2_opr: Оператор между topic1 и topic2 ('and'/'or')
            topic2_3_opr: Оператор между topic2 и topic3 ('and'/'or')
            topic0_2_opr: Оператор между topic0 и topic2 ('and'/'or')
            topic0_3_opr: Оператор между topic0 и topic3 ('and'/'or')
            topic1_3_opr: Оператор между topic1 и topic3 ('and'/'or')
            
        Returns:
            Dict[str, Any]: Словарь с логами
        """
        action = 'getLogs'
        
        params = {
            'module': self.module,
            'action': action,
            'address': address,
            'fromBlock': fromBlock,
            'toBlock': toBlock,
            'topic0': topic0,
            'topic1': topic1,
            'topic2': topic2,
            'topic3': topic3,
            'topic0_1_opr': topic0_1_opr,
            'topic1_2_opr': topic1_2_opr,
            'topic2_3_opr': topic2_3_opr,
            'topic0_2_opr': topic0_2_opr,
            'topic0_3_opr': topic0_3_opr,
            'topic1_3_opr': topic1_3_opr,
            'apikey': self.key,
        }
        self.logger.debug(f"Getting logs for address {address}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)


class Token(Module):
    """
    Класс для работы с модулем 'token' API блокчейн-сканера.
    """
    module: str = 'token'
    
    async def tokeninfo(self, contractaddress: str) -> Dict[str, Any]:
        """
        Получает информацию о токене.
        
        Args:
            contractaddress: Адрес контракта токена
            
        Returns:
            Dict[str, Any]: Словарь с информацией о токене
        """
        action = 'tokeninfo'
        
        params = {
            'module': self.module,
            'action': action,
            'contractaddress': contractaddress,
            'apikey': self.key,
        }
        self.logger.debug(f"Getting token info for {contractaddress}")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)


class Gastracker(Module):
    """
    Класс для работы с модулем 'gastracker' API блокчейн-сканера.
    """
    module: str = 'gastracker'
    
    async def gasoracle(self) -> Dict[str, Any]:
        """
        Получает оракул для текущих цен на газ.
        
        Returns:
            Dict[str, Any]: Словарь с текущими ценами на газ
        """
        action = 'gasoracle'
        
        params = {
            'module': self.module,
            'action': action,
            'apikey': self.key,
        }
        self.logger.debug("Getting gas oracle")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)


class Stats(Module):
    """
    Класс для работы с модулем 'stats' API блокчейн-сканера.
    """
    module: str = 'stats'
    
    async def ethprice(self) -> Dict[str, Any]:
        """
        Получает текущую цену эфира.
        
        Returns:
            Dict[str, Any]: Словарь с текущей ценой эфира
        """
        action = 'ethprice'
        
        params = {
            'module': self.module,
            'action': action,
            'apikey': self.key,
        }
        self.logger.debug("Getting ETH price")
        return await async_get(self.url, params=aiohttp_params(params), headers=self.headers)


class APIFunctions:
    """
    Класс для работы с API блокчейн-сканера.

    Attributes:
        key (str): API ключ.
        url (str): URL входной точки API.
        headers (Dict[str, Any]): Заголовки для запросов.
        account (Account): Функции для работы с модулем 'account'.
        contract (Contract): Функции для работы с модулем 'contract'.
        transaction (Transaction): Функции для работы с модулем 'transaction'.
        block (Block): Функции для работы с модулем 'block'.
        logs (Logs): Функции для работы с модулем 'logs'.
        token (Token): Функции для работы с модулем 'token'.
        gastracker (Gastracker): Функции для работы с модулем 'gastracker'.
        stats (Stats): Функции для работы с модулем 'stats'.
    """

    def __init__(self, key: str, url: str) -> None:
        """
        Инициализирует класс.

        Args:
            key (str): API ключ.
            url (str): URL входной точки API.
        """
        self.key = key
        self.url = url
        self.headers = {'content-type': 'application/json', 'user-agent': UserAgent().chrome}
        self.account = Account(self.key, self.url, self.headers)
        self.contract = Contract(self.key, self.url, self.headers)
        self.transaction = Transaction(self.key, self.url, self.headers)
        self.block = Block(self.key, self.url, self.headers)
        self.logs = Logs(self.key, self.url, self.headers)
        self.token = Token(self.key, self.url, self.headers)
        self.gastracker = Gastracker(self.key, self.url, self.headers)
        self.stats = Stats(self.key, self.url, self.headers)
