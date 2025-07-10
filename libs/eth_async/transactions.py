from __future__ import annotations
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union
from hexbytes import HexBytes
import asyncio
import time

from web3 import AsyncWeb3
from web3.middleware import combine_middleware
from web3.types import TxReceipt, TxParams, BlockIdentifier
from eth_account.datastructures import SignedTransaction

from .data import types
from . import exceptions
from .classes import AutoRepr
from .utils.utils import api_key_required
from .data.models import TokenAmount, CommonValues, TxArgs
from .exceptions import TransactionReverted

if TYPE_CHECKING:
    from .client import Client


class Tx(AutoRepr):
    """
    Инстанс транзакции для удобного выполнения действий с ней.

    Attributes:
        hash (Optional[HexBytes]): Хеш транзакции
        params (Optional[dict]): Параметры транзакции
        receipt (Optional[TxReceipt]): Чек транзакции
        function_identifier (Optional[str]): Идентификатор функции
        input_data (Optional[Dict[str, Any]]): Входные данные
    """
    hash: HexBytes | None
    params: dict | None
    receipt: TxReceipt | None
    function_identifier: str | None
    input_data: dict[str, Any] | None

    def __init__(self, tx_hash: str | HexBytes | None = None, params: dict | None = None) -> None:
        """
        Инициализирует класс.

        Args:
            tx_hash (Optional[Union[str, HexBytes]]): Хеш транзакции (None)
            params (Optional[dict]): Словарь с параметрами транзакции (None)
        """
        if not tx_hash and not params:
            raise exceptions.TransactionException("Specify 'tx_hash' or 'params' argument values!")

        if isinstance(tx_hash, str):
            tx_hash = HexBytes(tx_hash)

        self.hash = tx_hash
        self.params = params
        self.receipt = None
        self.function_identifier = None
        self.input_data = None

    async def parse_params(self, client) -> dict[str, Any]:
        """
        Парсит параметры отправленной транзакции.

        Args:
            client (Client): Инстанс Client

        Returns:
            Dict[str, Any]: Параметры отправленной транзакции
        """
        tx_data = await client.w3.eth.get_transaction(transaction_hash=self.hash)
        self.params = {
            'chainId': client.network.chain_id,
            'nonce': int(tx_data.get('nonce')),
            'gasPrice': int(tx_data.get('gasPrice')),
            'gas': int(tx_data.get('gas')),
            'from': tx_data.get('from'),
            'to': tx_data.get('to'),
            'data': tx_data.get('input'),
            'value': int(tx_data.get('value'))
        }
        return self.params

    async def wait_for_receipt(
            self, client, timeout: int | float = 120, poll_latency: float = 0.1
    ) -> dict[str, Any]:
        """
        Ожидает чек транзакции.

        Args:
            client (Client): Инстанс Client
            timeout (Union[int, float]): Таймаут ожидания чека (120 сек)
            poll_latency (float): Частота опроса (0.1 сек)

        Returns:
            Dict[str, Any]: Чек транзакции
        """
        if self.hash:
            client.logger.info(f"Waiting for receipt of transaction {self.hash.hex()}")
            self.receipt = await client.transactions.wait_for_receipt(
                w3=client.w3,
                tx_hash=self.hash,
                timeout=timeout,
                poll_latency=poll_latency
            )
            if self.receipt:
                client.logger.info(f"Transaction {self.hash.hex()} confirmed in block {self.receipt.get('blockNumber')}")
                return self.receipt
        
    async def wait_for_confirmations(
        self, client, confirmations: int = 1, timeout: int = 300, poll_latency: float = 0.1
    ) -> dict:
        """
        Ожидает указанное количество подтверждений для транзакции.
        
        Args:
            client (Client): Инстанс Client
            confirmations: Требуемое количество подтверждений
            timeout: Таймаут в секундах
            poll_latency: Интервал проверки в секундах
        
        Returns:
            dict: Чек транзакции с дополнительным полем confirmations
        """
        start_time = time.time()
        receipt = None
        if self.hash: 
            client.logger.info(f"Waiting for {confirmations} confirmations for transaction {self.hash.hex()}")
        
        while time.time() - start_time < timeout:
            try:
                receipt = await client.w3.eth.get_transaction_receipt(self.hash)
                current_block = await client.w3.eth.block_number
                
                if receipt and receipt['blockNumber'] is not None:
                    conf = current_block - receipt['blockNumber'] + 1
                    if conf >= confirmations:
                        receipt['confirmations'] = conf
                        self.receipt = receipt
                        if self.hash:
                            client.logger.info(f"Transaction {self.hash.hex()} confirmed with {conf} confirmations")
                        return receipt
                        
            except Exception as e:
                # Транзакция еще не в блокчейне
                client.logger.debug(f"Transaction not yet mined: {str(e)}")
                pass
                
            await asyncio.sleep(poll_latency)
            
        if receipt:
            current_block = await client.w3.eth.block_number
            receipt['confirmations'] = current_block - receipt['blockNumber'] + 1
            self.receipt = receipt
            
        if self.hash:
            raise exceptions.TransactionNotConfirmed(f"Timeout waiting for {confirmations} confirmations on {self.hash.hex()}")

    async def decode_input_data(self, client):
        """
        Декодирует входные данные транзакции.
        
        Args:
            client (Client): Инстанс Client
            
        Returns:
            Dict[str, Any]: Декодированные данные
        """
        data = None
        to_address = None
        if not self.params:
            await self.parse_params(client)
            
        else: 
            data = self.params.get('data')
            to_address = self.params.get('to')
        
        if not data or not to_address:
            return None
            
        try:
            # Получаем ABI контракта
            contract_abi = await client.contracts.get_abi_from_explorer(to_address)
            contract = await client.contracts.get(to_address, abi=contract_abi)
            
            # Получаем функцию по селектору
            function_selector = data[:10]  # первые 10 символов (0x + 8 символов)
            
            for fn in contract.abi:
                if fn['type'] == 'function':
                    fn_selector = contract.get_function_by_name(fn['name']).selector.hex()
                    if fn_selector == function_selector[2:]:  # Убираем '0x'
                        self.function_identifier = fn['name']
                        # Декодируем аргументы
                        self.input_data = contract.decode_function_input(data)
                        return self.input_data
            
            client.logger.warning(f"Could not identify function selector {function_selector}")
            return None
            
        except Exception as e:
            client.logger.error(f"Error decoding input data: {str(e)}")
            return None

    async def cancel(self, client, gas_price_multiplier: float = 1.1) -> Tx:
        """
        Отменяет транзакцию, отправляя новую с тем же nonce и нулевой стоимостью.
        
        Args:
            client (Client): Инстанс Client
            gas_price_multiplier: Множитель для увеличения газовой цены
            
        Returns:
            Tx: Инстанс новой транзакции
        """
        if not self.params:
            await self.parse_params(client)
            
        if self.hash: client.logger.info(f"Attempting to cancel transaction {self.hash.hex()}") 
        
        # Создаем транзакцию с тем же nonce, но отправляем на свой адрес с нулевой стоимостью
        if self.params:
            cancel_params = {
                'chainId': self.params.get('chainId'),
                'from': client.account.address,
                'to': client.account.address,
                'value': 0,
                'nonce': self.params.get('nonce'),
                'data': '0x'
            }
            
            # Устанавливаем более высокую цену газа
            if 'gasPrice' in self.params:
                cancel_params['gasPrice'] = int(self.params.get('gasPrice') * gas_price_multiplier)
            elif 'maxFeePerGas' in self.params:
                cancel_params['maxFeePerGas'] = int(self.params.get('maxFeePerGas') * gas_price_multiplier)
                cancel_params['maxPriorityFeePerGas'] = int(self.params.get('maxPriorityFeePerGas') * gas_price_multiplier)
                
            # Оцениваем газ
            cancel_params['gas'] = await client.w3.eth.estimate_gas(cancel_params)
            
            # Отправляем транзакцию отмены
            cancel_tx = await client.transactions.sign_and_send(tx_params=cancel_params)
            
            client.logger.info(f"Cancel transaction sent: {cancel_tx.hash.hex()}")
            return cancel_tx

    async def speed_up(self, client, gas_price_multiplier: float = 1.2) -> Tx | None:
        """
        Ускоряет транзакцию, отправляя новую с тем же nonce и данными, но с более высокой ценой газа.
        
        Args:
            client (Client): Инстанс Client
            gas_price_multiplier: Множитель для увеличения газовой цены
            
        Returns:
            Tx: Инстанс новой транзакции
        """
        if not self.params:
            await self.parse_params(client)
            
        if self.hash: client.logger.info(f"Attempting to speed up transaction {self.hash.hex()}")
        
        # Копируем параметры исходной транзакции
        if self.params:
            speed_up_params = self.params.copy()
            
            # Устанавливаем более высокую цену газа
            if 'gasPrice' in speed_up_params:
                speed_up_params['gasPrice'] = int(speed_up_params['gasPrice'] * gas_price_multiplier)
            elif 'maxFeePerGas' in speed_up_params:
                speed_up_params['maxFeePerGas'] = int(speed_up_params['maxFeePerGas'] * gas_price_multiplier)
                speed_up_params['maxPriorityFeePerGas'] = int(speed_up_params['maxPriorityFeePerGas'] * gas_price_multiplier)
                
            # Отправляем ускоренную транзакцию
            speed_up_tx = await client.transactions.sign_and_send(tx_params=speed_up_params)
            
            client.logger.info(f"Speed up transaction sent: {speed_up_tx.hash.hex()}")
            return speed_up_tx


class Transactions:
    def __init__(self, client: Client) -> None:
        self.client = client
        self.logger = self.client.logger

    async def gas_price(self) -> TokenAmount:
        """
        Получает текущую цену газа
        
        Returns:
            TokenAmount: Цена газа
        """
        gas_price = await self.client.w3.eth.gas_price
        return TokenAmount(amount=gas_price, wei=True)

    async def max_priority_fee(self, block: dict | None = None) -> TokenAmount:
        """
        Получает максимальную приоритетную плату.
        
        Args:
            block: Блок для анализа (опционально)
            
        Returns:
            TokenAmount: Максимальная приоритетная плата
        """
        try:
            # Попробуем использовать eth_maxPriorityFeePerGas RPC метод
            max_priority_fee = await self.client.w3.eth.max_priority_fee
            return TokenAmount(amount=max_priority_fee, wei=True)
        except Exception as e:
            self.logger.debug(f"eth_maxPriorityFeePerGas not available: {str(e)}")
            
            # Fallback к старому методу
            if not block:
                block = await self.client.w3.eth.get_block(block_identifier="latest")

            block_number = block['number']
            latest_block_transaction_count = await self.client.w3.eth.get_block_transaction_count(block_number)
            
            max_priority_fee_per_gas_lst = []
            for i in range(latest_block_transaction_count):
                try:
                    transaction = await self.client.w3.eth.get_transaction_by_block(block_number, i)
                    if 'maxPriorityFeePerGas' in transaction:
                        max_priority_fee_per_gas_lst.append(transaction['maxPriorityFeePerGas'])
                except Exception:
                    continue

            if not max_priority_fee_per_gas_lst:
                # Если не нашли ни одной транзакции с maxPriorityFeePerGas, вернем минимальное значение
                return TokenAmount(amount=1000000000, wei=True)  # 1 gwei
            else:
                max_priority_fee_per_gas_lst.sort()
                max_priority_fee_per_gas = max_priority_fee_per_gas_lst[len(max_priority_fee_per_gas_lst) // 2]
                return TokenAmount(amount=max_priority_fee_per_gas, wei=True)

    async def estimate_gas(self, tx_params: TxParams) -> TokenAmount:
        """
        Получает estimate gas limit для транзакции с указанными параметрами.
        
        Args:
            tx_params (TxParams): параметры транзакции
            
        Returns:
            TokenAmount: estimate gas
        """
        estimate = await self.client.w3.eth.estimate_gas(transaction=tx_params)
        # Добавим 10% запаса для надежности
        gas_with_buffer = int(estimate * 1.1)
        return TokenAmount(amount=gas_with_buffer, wei=True)

    async def auto_add_params(self, tx_params: TxParams) -> TxParams:
        """
        Добавляет параметры 'chainId', 'nonce', 'from', 'gasPrice' или 'maxFeePerGas' + 'maxPriorityFeePerGas' и 'gas'
        к параметрам транзакции, если они отсутствуют.
        
        Args:
            tx_params (TxParams): параметры транзакции
            
        Returns:
            TxParams: параметры транзакции с добавленными значениями
        """
        self.logger.debug("Auto-adding transaction parameters")

        if 'chainId' not in tx_params:
            tx_params['chainId'] = self.client.network.chain_id

        if not tx_params.get('nonce'):
            tx_params['nonce'] = await self.client.wallet.nonce()

        if 'from' not in tx_params:
            tx_params['from'] = self.client.account.address

        # Выбираем тип транзакции в зависимости от настроек сети
        if 'gasPrice' not in tx_params and 'maxFeePerGas' not in tx_params:
            if self.client.network.tx_type == 2:  # EIP-1559
                # Для EIP-1559 устанавливаем maxFeePerGas и maxPriorityFeePerGas
                gas_price = (await self.gas_price()).Wei
                priority_fee = (await self.max_priority_fee()).Wei
                
                tx_params['maxFeePerGas'] = gas_price
                tx_params['maxPriorityFeePerGas'] = priority_fee
            else:
                # Для старых транзакций просто устанавливаем gasPrice
                tx_params['gasPrice'] = (await self.gas_price()).Wei

        elif 'gasPrice' in tx_params and not int(tx_params['gasPrice']):
            tx_params['gasPrice'] = (await self.gas_price()).Wei

        if 'maxFeePerGas' in tx_params and 'maxPriorityFeePerGas' not in tx_params:
            tx_params['maxPriorityFeePerGas'] = await self.max_priority_fee()
            # Проверяем, чтобы maxFeePerGas был больше или равен maxPriorityFeePerGas
            if tx_params['maxFeePerGas'] < tx_params['maxPriorityFeePerGas']:
                tx_params['maxFeePerGas'] = tx_params['maxPriorityFeePerGas'] * 1.01

        # Оцениваем gas, если не указан
        if 'gas' not in tx_params or not int(tx_params['gas']):
            try:
                tx_params['gas'] = (await self.estimate_gas(tx_params=tx_params)).Wei
            except Exception as e:
                self.logger.error(f"Failed to estimate gas: {str(e)}")
                if 'revert' in str(e):
                    raise TransactionReverted(message=str(e))
                # Устанавливаем стандартный лимит газа, если не удалось оценить
                tx_params['gas'] = 250000

        self.logger.debug(f"Final transaction parameters: {tx_params}")
        return tx_params

    async def sign_transaction(self, tx_params: TxParams) -> SignedTransaction:
        """
        Подписывает транзакцию.
        
        Args:
            tx_params (TxParams): параметры транзакции
            
        Returns:
            SignedTransaction: подписанная транзакция
        """
        return self.client.w3.eth.account.sign_transaction(
            transaction_dict=tx_params, private_key=self.client.account.key
        )

    async def sign_and_send(self, tx_params: TxParams) -> Tx:
        """
        Подписывает и отправляет транзакцию. Дополнительно добавляет параметры 'chainId', 'nonce', 'from',
        'gasPrice' или 'maxFeePerGas' + 'maxPriorityFeePerGas' и 'gas' к параметрам транзакции, если они отсутствуют.
        
        Args:
            tx_params (TxParams): параметры транзакции
            
        Returns:
            Tx: инстанс отправленной транзакции
        """
        tx_params = await self.auto_add_params(tx_params=tx_params)
        
        self.logger.info(f"Signing transaction: {tx_params}")
        signed_tx = await self.sign_transaction(tx_params)
        
        self.logger.info(f"Sending raw transaction")
        tx_hash = await self.client.w3.eth.send_raw_transaction(transaction=signed_tx.raw_transaction)
        
        self.logger.info(f"Transaction sent: {tx_hash.hex()}")
        return Tx(tx_hash=tx_hash, params=tx_params)
        
    async def send_eip1559_transaction(self, tx_params: dict) -> Tx:
        """
        Отправляет транзакцию типа EIP-1559 (тип 2) с поддержкой maxFeePerGas и maxPriorityFeePerGas.
        
        Args:
            tx_params: Параметры транзакции
        
        Returns:
            Tx: Инстанс отправленной транзакции
        """
        if self.client.network.tx_type != 2:
            self.logger.warning(f"Network {self.client.network.name} does not support EIP-1559 transactions")
            
        if 'gasPrice' in tx_params:
            self.logger.warning("Remove 'gasPrice' from parameters when using EIP-1559 transaction")
            del tx_params['gasPrice']
            
        # Если не указаны необходимые параметры, добавляем их
        if 'maxFeePerGas' not in tx_params or 'maxPriorityFeePerGas' not in tx_params:
            gas_strategy = GasStrategy(self.client)
            max_fee, max_priority_fee = await gas_strategy.estimate_eip1559_fees()
            
            if 'maxFeePerGas' not in tx_params:
                tx_params['maxFeePerGas'] = max_fee
                
            if 'maxPriorityFeePerGas' not in tx_params:
                tx_params['maxPriorityFeePerGas'] = max_priority_fee
                
        return await self.sign_and_send(tx_params=tx_params)

    async def approved_amount(
            self, token: types.Contract, spender: types.Contract, owner: types.Address | None = None
    ) -> TokenAmount:
        """
        Получает одобренное количество токена.
        
        Args:
            token (Contract): адрес контракта или инстанс токена
            spender (Contract): адрес спендера, адрес контракта или инстанс
            owner (Optional[Address]): адрес владельца (импортированный в клиент адрес)
            
        Returns:
            TokenAmount: одобренное количество
        """
        contract_address, abi = await self.client.contracts.get_contract_attributes(token)
        contract = await self.client.contracts.default_token(contract_address)
        spender, abi = await self.client.contracts.get_contract_attributes(spender)
        if not owner:
            owner = self.client.account.address

        return TokenAmount(
            amount=await contract.functions.allowance(
                AsyncWeb3.to_checksum_address(owner),
                AsyncWeb3.to_checksum_address(spender)
            ).call(),
            decimals=await self.client.transactions.get_decimals(contract=contract.address),
            wei=True
        )

    @staticmethod
    async def wait_for_receipt(
            w3: AsyncWeb3, tx_hash: str | HexBytes, timeout: int | float = 120, poll_latency: float = 0.1
    ) -> dict[str, Any]:
        """
        Ожидает чек транзакции.
        
        Args:
            w3: веб3 объект
            tx_hash (Union[str, HexBytes]): хеш транзакции
            timeout (Union[int, float]): таймаут ожидания чека (120)
            poll_latency (float): частота опроса (0.1 сек)
            
        Returns:
            Dict[str, Any]: чек транзакции
        """
        return dict(await w3.eth.wait_for_transaction_receipt(
            transaction_hash=tx_hash, timeout=timeout, poll_latency=poll_latency
        ))

    async def approve(
            self, token: types.Contract, spender: types.Address, amount: types.Amount | None = None,
            gas_limit: types.GasLimit | None = None, nonce: int | None = None, from_address: types.Address | None = None
    ) -> Tx:
        """
        Одобряет трату токена для указанного адреса.
        
        Args:
            token (Contract): адрес контракта или инстанс токена для одобрения
            spender (Address): адрес спендера, адрес контракта или инстанс
            amount (Optional[TokenAmount]): количество для одобрения (бесконечность)
            gas_limit (Optional[GasLimit]): газовый лимит в Wei (парсится из сети)
            nonce (Optional[int]): nonce адреса отправителя (получается с помощью функции 'nonce')
            from_address (Optional[Address]): адрес отправителя
            
        Returns:
            Tx: инстанс отправленной транзакции
        """
        spender = AsyncWeb3.to_checksum_address(spender)
        contract_address, abi = await self.client.contracts.get_contract_attributes(token)
        contract = await self.client.contracts.default_token(contract_address)

        if amount is None:
            amount = CommonValues.InfinityInt
        elif isinstance(amount, (int, float)):
            amount = TokenAmount(
                amount=amount,
                decimals=await self.client.transactions.get_decimals(contract=contract.address)
            ).Wei
        else:
            amount = amount.Wei

        tx_args = TxArgs(
            spender=spender,
            amount=amount
        )

        tx_params = {
            'nonce': nonce,
            'to': contract.address,
            # Обновлено на encode_abi для web3.py 7.x
            'data': contract.encode_abi('approve', args=tx_args.tuple())
        }
        if from_address:
            tx_params['from'] = from_address
        if gas_limit:
            if isinstance(gas_limit, int):
                gas_limit = TokenAmount(amount=gas_limit, wei=True)
            tx_params['gas'] = gas_limit.Wei

        self.logger.info(f"Approving {amount} tokens for {spender}")
        return await self.sign_and_send(tx_params=tx_params)

    async def get_decimals(self, contract: types.Contract) -> int:
        """
        Получает количество десятичных знаков токена.
        
        Args:
            contract: Адрес или инстанс контракта
            
        Returns:
            int: Количество десятичных знаков
        """
        contract_address, abi = await self.client.contracts.get_contract_attributes(contract)
        contract = await self.client.contracts.default_token(contract_address=contract_address)
        return await contract.functions.decimals().call()

    async def sign_message(self, message: str) -> HexBytes:
        """
        Подписывает сообщение.
        
        Args:
            message: Сообщение для подписи
            
        Returns:
            HexBytes: Подпись
        """
        message_hash = AsyncWeb3.keccak(text=message)
        signed_message = self.client.w3.eth.account.sign_message(
            message_hash=message_hash,
            private_key=self.client.account.key
        )
        return signed_message.signature

    @staticmethod
    async def decode_input_data(contract: AsyncContract, tx_data: str) -> dict:
        """
        Декодирует входные данные транзакции.
        
        Args:
            contract: Инстанс контракта
            tx_data: Данные транзакции
            
        Returns:
            dict: Декодированные данные
        """
        return contract.decode_function_input(tx_data)

    @api_key_required
    async def find_txs(
            self, contract: types.Contract | list[types.Contract], function_name: str | None = '',
            address: types.Address | None = None, after_timestamp: int = 0, before_timestamp: int = 999_999_999_999
    ) -> dict[str, ...]:
        """
        Находит все транзакции взаимодействия с контрактом, дополнительно можно отфильтровать транзакции
        по имени функции контракта.
        
        Args:
            contract (Union[Contract, List[Contract]]): контракт или список контрактов, с которыми
                произошло взаимодействие
            function_name (Optional[str]): имя функции для сортировки (любое)
            address (Optional[Address]): адрес для получения списка транзакций (импортированный в клиент адрес)
            after_timestamp (int): после какого времени фильтровать транзакции (0)
            before_timestamp (int): до какого времени фильтровать транзакции (бесконечность)
            
        Returns:
            Dict[str, CoinTx]: найденные транзакции
        """
        contract_addresses = []
        if isinstance(contract, list):
            for contract_ in contract:
                contract_address, abi = await self.client.contracts.get_contract_attributes(contract_)
                contract_addresses.append(contract_address.lower())

        else:
            contract_address, abi = await self.client.contracts.get_contract_attributes(contract)
            contract_addresses.append(contract_address.lower())

        if not address:
            address = self.client.account.address

        txs = {}
        coin_txs = (await self.client.network.api.functions.account.txlist(address))['result']
        for tx in coin_txs:
            if (
                    after_timestamp < int(tx.get('timeStamp')) < before_timestamp and
                    tx.get('isError') == '0' and
                    tx.get('to') in contract_addresses and
                    function_name in tx.get('functionName')
            ):
                txs[tx.get('hash')] = tx

        return txs

    @api_key_required
    async def find_tx_by_method_id(self, address: str, to: str, method_id: str):
        """
        Находит транзакции по method ID.
        
        Args:
            address: Адрес для поиска транзакций
            to: Адрес получателя
            method_id: Method ID для поиска
            
        Returns:
            dict: Найденные транзакции
        """
        txs = {}
        coin_txs = (await self.client.network.api.functions.account.txlist(address))['result']
        for tx in coin_txs:
            if tx.get('isError') == '0' and tx.get('to') == to.lower() and tx.get('input').startswith(method_id):
                txs[tx.get('hash')] = tx
        return txs


class GasStrategy:
    """Стратегии для оценки газовой цены"""
    
    def __init__(self, client: Client):
        self.client = client
        
    async def estimate_eip1559_fees(self, block_count: int = 5) -> tuple:
        """
        Оценивает maxFeePerGas и maxPriorityFeePerGas на основе последних блоков.
        
        Args:
            block_count: Количество блоков для анализа
            
        Returns:
            tuple: (maxFeePerGas, maxPriorityFeePerGas)
        """
        try:
            # Получаем историю газовых цен
            fee_history = await self.client.w3.eth.fee_history(
                block_count, 'latest', [10, 50, 90]
            )
            
            # Используем 50-й процентиль для приоритетной платы
            priority_fees = [fee[1] for fee in fee_history['reward']]
            max_priority_fee = sum(priority_fees) // len(priority_fees)
            
            # Оцениваем maxFeePerGas
            base_fees = fee_history['baseFeePerGas']
            latest_base_fee = base_fees[-1]
            
            # Добавляем двукратный базовый сбор в качестве запаса
            max_fee = latest_base_fee * 2 + max_priority_fee
            
            return (max_fee, max_priority_fee)
        except Exception as e:
            self.client.logger.error(f"Error estimating EIP-1559 fees: {str(e)}")
            # Возвращаем дефолтные значения
            base_fee = await self.client.w3.eth.gas_price
            priority_fee = base_fee // 10  # Приоритетная плата - 10% от базовой
            return (base_fee * 2, priority_fee)
        
    async def estimate_gas_price_strategy(self, speed: str = 'medium') -> int:
        """
        Оценивает газовую цену на основе выбранной скорости.
        
        Args:
            speed: Скорость транзакции ('slow', 'medium', 'fast')
            
        Returns:
            int: Газовая цена в Wei
        """
        speed_percentiles = {
            'slow': 10,
            'medium': 50,
            'fast': 90
        }
        
        percentile = speed_percentiles.get(speed, 50)
        
        try:
            fee_history = await self.client.w3.eth.fee_history(5, 'latest', [percentile])
            gas_prices = []
            
            for i, reward in enumerate(fee_history['reward']):
                base_fee = fee_history['baseFeePerGas'][i]
                effective_gas = base_fee + reward[0]
                gas_prices.append(effective_gas)
                
            return sum(gas_prices) // len(gas_prices)
        except Exception as e:
            self.client.logger.error(f"Error estimating gas price: {str(e)}")
            # Возвращаем текущую газовую цену с учетом скорости
            gas_price = await self.client.w3.eth.gas_price
            multipliers = {
                'slow': 0.8,
                'medium': 1.0,
                'fast': 1.5
            }
            return int(gas_price * multipliers.get(speed, 1.0))
