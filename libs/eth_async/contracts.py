from __future__ import annotations
from typing import TYPE_CHECKING, List, Dict, Any, Optional, Tuple, Union, cast
import json
import logging

from web3 import AsyncWeb3
from eth_typing import ChecksumAddress
from web3.contract import AsyncContract

from .data.models import DefaultABIs, RawContract
from .utils.web_requests import async_get
from .utils.strings import text_between
from .data import types
from .exceptions import APIException, ContractException

if TYPE_CHECKING:
    from .client import Client


class Contracts:
    """
    Класс для работы с контрактами Ethereum.
    """
    
    def __init__(self, client: Client) -> None:
        """
        Инициализирует класс Contracts.
        
        Args:
            client: Инстанс Client
        """
        self.client = client
        self.logger = self.client.logger

    async def default_token(self, contract_address: ChecksumAddress | str) -> AsyncContract:
        """
        Получает инстанс токен-контракта со стандартным набором функций.
        
        Args:
            contract_address: Адрес контракта токена
            
        Returns:
            AsyncContract: Инстанс контракта токена
        """
        self.logger.debug(f"Creating default token contract at {contract_address}")
        contract_address = AsyncWeb3.to_checksum_address(contract_address)
        return self.client.w3.eth.contract(address=contract_address, abi=DefaultABIs.Token)

    @staticmethod
    async def get_signature(hex_signature: str) -> list | None:
        """
        Находит все совпадающие сигнатуры в базе данных https://www.4byte.directory/.
        
        Args:
            hex_signature: Хеш сигнатуры
            
        Returns:
            list | None: Найденные совпадения
        """
        try:
            response = await async_get(f'https://www.4byte.directory/api/v1/signatures/?hex_signature={hex_signature}')
            results = response['results']
            return [m['text_signature'] for m in sorted(results, key=lambda result: result['created_at'])]

        except Exception as e:
            logging.error(f"Error getting signature for {hex_signature}: {str(e)}")
            return None

    @staticmethod
    async def parse_function(text_signature: str) -> dict:
        """
        Строит словарь функции для ABI на основе предоставленной текстовой сигнатуры.
        
        Args:
            text_signature: Текстовая сигнатура, например, approve(address,uint256)
            
        Returns:
            dict: Словарь функции для ABI
        """
        name, sign = text_signature.split('(', 1)
        sign = sign[:-1]
        tuples = []
        
        while '(' in sign:
            tuple_ = text_between(text=sign[:-1], begin='(', end=')')
            tuples.append(tuple_.split(',') or [])
            sign = sign.replace(f'({tuple_})', 'tuple')

        inputs = sign.split(',')
        if inputs == ['']:
            inputs = []

        function = {
            'type': 'function',
            'name': name,
            'inputs': [],
            'outputs': [{'type': 'uint256'}]
        }
        
        i = 0
        for type_ in inputs:
            input_ = {'type': type_}
            if type_ == 'tuple':
                input_['components'] = [{'type': comp_type} for comp_type in tuples[i]]
                i += 1

            function['inputs'].append(input_)

        return function

    @staticmethod
    async def get_contract_attributes(contract: types.Contract) -> tuple[ChecksumAddress, list | None]:
        """
        Преобразует различные типы контрактов в адрес и ABI.
        
        Args:
            contract: Адрес или инстанс контракта
            
        Returns:
            tuple[ChecksumAddress, list | None]: Адрес и ABI контракта
        """
        if isinstance(contract, (AsyncContract, RawContract)):
            return contract.address, contract.abi

        return AsyncWeb3.to_checksum_address(contract), None

    async def get(
        self, contract_address: types.Contract, abi: list | str | None = None, search_explorer: bool = False
    ) -> AsyncContract:
        """
        Получает инстанс контракта.
        
        Args:
            contract_address: Адрес или инстанс контракта
            abi: ABI контракта (опционально)
            
        Returns:
            AsyncContract: Инстанс контракта
        """
        contract_address, contract_abi = await self.get_contract_attributes(contract_address)
        
        if not abi and not contract_abi and search_explorer:
            # Пробуем получить ABI из блокчейн-сканера
            try:
                if self.client.network.api and self.client.network.api.functions:
                    self.logger.info(f"Attempting to fetch ABI from explorer for {contract_address}")
                    abi = await self.get_abi_from_explorer(contract_address)
                else:
                    raise ValueError('No API available to fetch ABI')
            except Exception as e:
                raise ValueError(f'Cannot get ABI for contract: {str(e)}')

        elif not abi and not contract_abi and not search_explorer:
                abi = DefaultABIs.Token
                abi = DefaultABIs.Token


        if not abi:
            abi = contract_abi

        if abi:
            self.logger.debug(f"Creating contract instance at {contract_address}")
            return self.client.w3.eth.contract(address=contract_address, abi=abi)

        raise ContractException(f"No ABI provided or found for contract {contract_address}")
        
    async def get_abi_from_explorer(self, contract_address: str) -> list:
        """
        Получает ABI контракта из блокчейн-сканера.
        
        Args:
            contract_address: Адрес контракта
            
        Returns:
            list: ABI контракта
        """
        if not self.client.network.api or not self.client.network.api.functions:
            raise APIException("API key is required to get contract ABI from explorer")
            
        response = await self.client.network.api.functions.contract.getabi(contract_address)
        
        if response.get('status') == '0':
            raise APIException(f"Failed to get ABI: {response.get('message')}")
            
        try:
            abi = json.loads(response.get('result', '[]'))
            return abi
        except Exception as e:
            raise APIException(f"Failed to parse ABI: {str(e)}")
            
    async def get_contract_events(
        self, contract: types.Contract, event_name: str = None, 
        from_block: int = 0, to_block: str = 'latest',
        argument_filters: dict = None
    ) -> list:
        """
        Получает события контракта с фильтрацией.
        
        Args:
            contract: Адрес или инстанс контракта
            event_name: Название события для фильтрации (или None для всех событий)
            from_block: Начальный блок
            to_block: Конечный блок
            argument_filters: Фильтры по аргументам события
            
        Returns:
            list: Список событий
        """
        self.logger.info(f"Fetching events for contract {contract}")
        contract_instance = await self.get(contract)
        
        event_filter = {}
        if event_name:
            event = getattr(contract_instance.events, event_name)
            event_filter = event.create_filter().filter_params
            
        if argument_filters:
            if 'topics' not in event_filter:
                event_filter['topics'] = []
            # Применяем фильтры по аргументам
            # (здесь нужна дополнительная логика для преобразования аргументов в topics)
            
        event_filter.update({
            'fromBlock': from_block,
            'toBlock': to_block,
            'address': contract_instance.address
        })
        
        self.logger.debug(f"Getting logs with filter: {event_filter}")
        logs = await self.client.w3.eth.get_logs(event_filter)
        
        # Парсинг событий с помощью ABI контракта
        processed_logs = []
        for log in logs:
            try:
                processed = contract_instance.events.process_log(log)
                processed_logs.append(processed)
            except Exception as e:
                self.logger.warning(f"Failed to process log: {str(e)}")
                processed_logs.append(log)
                
        self.logger.info(f"Found {len(processed_logs)} events")
        return processed_logs
