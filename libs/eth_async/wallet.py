from __future__ import annotations
from typing import TYPE_CHECKING, Dict, List, Optional, Union, Any
import asyncio

from web3 import AsyncWeb3
from eth_typing import ChecksumAddress
from web3.contract import AsyncContract

from .data.models import TokenAmount, RawContract
from .data import types
from .exceptions import WalletException, InsufficientFunds

if TYPE_CHECKING:
    from .client import Client


class Wallet:
    """
    Класс для работы с кошельком.
    """
    
    def __init__(self, client: Client) -> None:
        """
        Инициализирует класс Wallet.
        
        Args:
            client: Инстанс Client
        """
        self.client = client
        self.logger = self.client.logger

    async def balance(
            self,
            token: types.Contract | None = None,
            address: str | ChecksumAddress | None = None,
            decimals: int = 18
    ) -> TokenAmount:
        """
        Получает баланс эфира или токена.
        
        Args:
            token: Адрес или инстанс контракта токена (опционально)
            address: Адрес для проверки баланса (опционально)
            decimals: Количество десятичных знаков (для эфира - 18)
            
        Returns:
            TokenAmount: Баланс
        """
        if not address:
            address = self.client.account.address

        address = AsyncWeb3.to_checksum_address(address)

        if not token:
            # Получаем баланс эфира
            balance = await self.client.w3.eth.get_balance(account=address)
            return TokenAmount(
                amount=balance,
                decimals=decimals,
                wei=True
            )

        # Получаем баланс токена
        token_address = token
        if isinstance(token, (RawContract, AsyncContract)):
            token_address = token.address

        contract = await self.client.contracts.default_token(
            contract_address=AsyncWeb3.to_checksum_address(token_address)
        )

        balance = await contract.functions.balanceOf(address).call()
        decimals = await self.client.transactions.get_decimals(contract=contract.address)
        
        return TokenAmount(
            amount=balance,
            decimals=decimals,
            wei=True
        )

    async def nonce(self, address: ChecksumAddress | None = None) -> int:
        """
        Получает nonce адреса.
        
        Args:
            address: Адрес для получения nonce
            
        Returns:
            int: Nonce
        """
        if not address:
            address = self.client.account.address
        return await self.client.w3.eth.get_transaction_count(address)
        
    async def get_all_tokens(self, address: str | None = None) -> Dict[str, TokenAmount]:
        """
        Получает все токены на кошельке, используя API блокчейн-сканера.
        
        Args:
            address: Адрес для проверки (опционально)
            
        Returns:
            Dict[str, TokenAmount]: Словарь токенов {адрес: баланс}
        """
        if not address:
            address = self.client.account.address
            
        if not self.client.network.api or not self.client.network.api.functions:
            raise WalletException("API key is required to get token list")
            
        # Получаем список токенов через API блокчейн-сканера
        try:
            response = await self.client.network.api.functions.account.tokentx(
                contractaddress="",
                address=address,
                startblock=0
            )
            
            if response.get('status') == '0':
                self.logger.warning(f"Failed to get token list: {response.get('message')}")
                return {}
                
            tokens = {}
            unique_tokens = set()
            
            # Получаем уникальные токены из списка транзакций
            for tx in response.get('result', []):
                contract_address = AsyncWeb3.to_checksum_address(tx.get('contractAddress'))
                if contract_address not in unique_tokens:
                    unique_tokens.add(contract_address)
                    
            # Проверяем баланс каждого токена
            tasks = []
            for token_address in unique_tokens:
                tasks.append(self.balance(token=token_address, address=address))
                
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, token_address in enumerate(unique_tokens):
                if isinstance(results[i], Exception):
                    self.logger.warning(f"Failed to get balance for {token_address}: {str(results[i])}")
                    continue
                    
                if results[i].Wei > 0:
                    tokens[token_address] = results[i]
                    
            return tokens
                
        except Exception as e:
            self.logger.error(f"Error getting token list: {str(e)}")
            return {}

    async def transfer(
        self, to_address: str, amount: types.Amount, token: types.Contract = None,
        gas_limit: types.GasLimit = None, nonce: int = None
    ) -> Tx:
        """
        Переводит эфир или токен на указанный адрес.
        
        Args:
            to_address: Адрес получателя
            amount: Количество для перевода
            token: Адрес или инстанс контракта токена (опционально, если не указан - эфир)
            gas_limit: Лимит газа (опционально)
            nonce: Nonce (опционально)
            
        Returns:
            Tx: Инстанс отправленной транзакции
        """
        from .transactions import Tx  # Импортируем здесь для избежания циклических импортов
        
        to_address = AsyncWeb3.to_checksum_address(to_address)
        self.logger.info(f"Transferring {'ETH' if token is None else 'token'} to {to_address}")
        
        if token is None:
            # Перевод эфира
            if isinstance(amount, (int, float)):
                amount_wei = self.client.w3.to_wei(amount, 'ether')
            elif isinstance(amount, TokenAmount):
                amount_wei = amount.Wei
            else:
                amount_wei = amount
                
            # Проверяем баланс
            balance = await self.balance()
            if balance.Wei < amount_wei:
                raise InsufficientFunds(f"Insufficient ETH balance: {balance.Ether} ETH, needed: {self.client.w3.from_wei(amount_wei, 'ether')} ETH")
                
            tx_params = {
                'to': to_address,
                'value': amount_wei,
                'nonce': nonce
            }
            
            if gas_limit:
                if isinstance(gas_limit, int):
                    gas_limit = TokenAmount(amount=gas_limit, wei=True)
                tx_params['gas'] = gas_limit.Wei
                
            return await self.client.transactions.sign_and_send(tx_params=tx_params)
        else:
            # Перевод токена
            contract_address, abi = await self.client.contracts.get_contract_attributes(token)
            contract = await self.client.contracts.default_token(contract_address)
            
            # Получаем количество десятичных знаков и конвертируем сумму
            decimals = await self.client.transactions.get_decimals(contract=contract.address)
            
            if isinstance(amount, (int, float)):
                amount_wei = TokenAmount(amount=amount, decimals=decimals).Wei
            elif isinstance(amount, TokenAmount):
                amount_wei = amount.Wei
            else:
                amount_wei = amount
                
            # Проверяем баланс токена
            balance = await self.balance(token=contract_address)
            if balance.Wei < amount_wei:
                raise InsufficientFunds(f"Insufficient token balance: {balance.Ether}, needed: {TokenAmount(amount=amount_wei, decimals=decimals, wei=True).Ether}")
                
            # Создаем аргументы для transfer
            from .data.models import TxArgs
            tx_args = TxArgs(
                to=to_address,
                value=amount_wei
            )
            
            # Создаем параметры транзакции
            tx_params = {
                'to': contract.address,
                'data': contract.encode_abi('transfer', args=tx_args.tuple()),
                'nonce': nonce
            }
            
            if gas_limit:
                if isinstance(gas_limit, int):
                    gas_limit = TokenAmount(amount=gas_limit, wei=True)
                tx_params['gas'] = gas_limit.Wei
                
            return await self.client.transactions.sign_and_send(tx_params=tx_params)
            
    async def check_allowance(
        self, token: types.Contract, spender: types.Contract, 
        amount: types.Amount = None, approve_if_needed: bool = False
    ) -> bool:
        """
        Проверяет, одобрено ли достаточное количество токенов для указанного спендера.
        
        Args:
            token: Адрес или инстанс контракта токена
            spender: Адрес спендера
            amount: Требуемое количество (опционально)
            approve_if_needed: Автоматически одобрить, если текущего одобрения недостаточно
            
        Returns:
            bool: True, если достаточно одобрено
        """
        # Получаем текущее одобрение
        current_allowance = await self.client.transactions.approved_amount(
            token=token, 
            spender=spender,
            owner=self.client.account.address
        )
        
        # Если amount не указан, просто возвращаем текущее одобрение
        if amount is None:
            return current_allowance.Wei > 0
            
        # Конвертируем amount в Wei
        contract_address, _ = await self.client.contracts.get_contract_attributes(token)
        decimals = await self.client.transactions.get_decimals(contract=contract_address)
        
        if isinstance(amount, (int, float)):
            amount_wei = TokenAmount(amount=amount, decimals=decimals).Wei
        elif isinstance(amount, TokenAmount):
            amount_wei = amount.Wei
        else:
            amount_wei = amount
            
        # Проверяем, достаточно ли одобрено
        is_approved = current_allowance.Wei >= amount_wei
        
        # Если недостаточно одобрено и нужно автоматически одобрить
        if not is_approved and approve_if_needed:
            self.logger.info(f"Insufficient allowance: {current_allowance.Ether}, needed: {TokenAmount(amount=amount_wei, decimals=decimals, wei=True).Ether}")
            self.logger.info(f"Approving tokens for {spender}")
            
            # Одобряем токены
            tx = await self.client.transactions.approve(
                token=token,
                spender=spender,
                amount=None  # Бесконечное одобрение
            )
            
            # Ждем подтверждения транзакции
            await tx.wait_for_receipt(self.client)
            
            # Проверяем одобрение снова
            current_allowance = await self.client.transactions.approved_amount(
                token=token, 
                spender=spender,
                owner=self.client.account.address
            )
            
            is_approved = current_allowance.Wei >= amount_wei
            
        return is_approved           
