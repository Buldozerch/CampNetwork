from libs.eth_async import create_client
import random
from libs.eth_async.data.models import TxArgs
from data.contracts import Contracts
from data.config import ACTUAL_NFT_MINT
from libs.eth_async import TokenAmount
from web3.constants import MAX_INT
from data.models import Settings
from web3.contract import AsyncContract, Contract
from web3.types import TxParams
from typing import Dict, Optional, Any, Union
from loguru import logger
from dataclasses import dataclass
import asyncio
from utils.db_api_async.models import User

ETH_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
F_ADDRESS = "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"


@dataclass
class TransactionResult:
    """Результат выполнения транзакции"""

    success: bool
    tx_hash: Optional[str] = None
    error_message: Optional[str] = None
    receipt: Optional[Dict] = None


class CampOnchain:
    def __init__(self, user: User) -> None:
        self.user = user
        self.client = create_client(
            private_key=user.private_key, network="camp", proxy=user.proxy
        )

    async def handle_mint(self):
        settings = Settings()
        start_delay, end_delay = settings.get_quest_delay()
        base_camp_contract = await self.client.contracts.get(
            contract_address=Contracts.BASE_CAMP
        )
        base_camp_max_mint = 50
        aura_contract = await self.client.contracts.get(contract_address=Contracts.AURA)
        aura_max_mint = 50
        sticky_pleb_contract = await self.client.contracts.get(
            contract_address=Contracts.STICKY_PLEB
        )
        sticky_pleb_max_mint = 1
        climb_contract = await self.client.contracts.get(
            contract_address=Contracts.CLIMB
        )
        climb_max_mint = 50
        pictographs_contract = await self.client.contracts.get(
            contract_address=Contracts.PICTOGRAPHS
        )
        pictographs_max_mint = 1
        token_tails_max_mint = 1
        token_tails_contract = await self.client.contracts.get(
            contract_address=Contracts.TOKEN_TAILS
        )

        omnihub_max_mint = 1
        omnihub_contract = await self.client.contracts.get(
            contract_address=Contracts.OMNI_HUB
        )

        tavern_quest_max_mint = 1
        tavern_quest_contract = await self.client.contracts.get(
            contract_address=Contracts.TAVERN_QUEST
        )
        mintpad_max_mint = 1
        mintpad_contract = await self.client.contracts.get(
            contract_address=Contracts.MINT_PAD
        )
        actual_nft_mint = random.sample(ACTUAL_NFT_MINT, len(ACTUAL_NFT_MINT))
        for mint in actual_nft_mint:
            if mint == "base_camp":
                need_mint, quantity = await self.need_mint_and_quantity(
                    contract=base_camp_contract, max_mint=base_camp_max_mint
                )
                if need_mint and quantity:
                    await self.base_camp_mint(
                        contract=base_camp_contract, quantity=quantity
                    )
                else:
                    continue

            elif mint == "mintpad":
                need_mint, quantity = await self.need_mint_and_quantity(
                    contract=mintpad_contract, max_mint=mintpad_max_mint
                )
                if need_mint and quantity:
                    await self.mintpad_mint(
                        contract=mintpad_contract
                    )
                else:
                    continue

            elif mint == "tavern_quest":
                need_mint, quantity = await self.need_mint_and_quantity(
                    contract=tavern_quest_contract, max_mint=tavern_quest_max_mint
                )
                if need_mint and quantity:
                    await self.tavern_quest_mint(
                        contract=tavern_quest_contract
                    )
                else:
                    continue

            elif mint == "omnihub_mint":
                need_mint, quantity = await self.need_mint_and_quantity(
                    contract=omnihub_contract, max_mint=omnihub_max_mint
                )
                if need_mint and quantity:
                    await self.omnihub_mint(
                        contract=omnihub_contract
                    )
                else:
                    continue

            elif mint == "aura":
                need_mint, quantity = await self.need_mint_and_quantity(
                    contract=aura_contract, max_mint=aura_max_mint
                )
                if need_mint and quantity:
                    await self.aura_mint(contract=aura_contract, quantity=quantity)
                else:
                    continue

            elif mint == "sticky_pleb":
                need_mint, quantity = await self.need_mint_and_quantity(
                    contract=sticky_pleb_contract, max_mint=sticky_pleb_max_mint
                )
                if need_mint and quantity:
                    await self.sticky_pleb_mint(
                        contract=sticky_pleb_contract, quantity=quantity
                    )
                else:
                    continue

            elif mint == "climb":
                need_mint, quantity = await self.need_mint_and_quantity(
                    contract=climb_contract, max_mint=climb_max_mint
                )
                if need_mint and quantity:
                    await self.climb_mint(contract=climb_contract, quantity=quantity)
                else:
                    continue

            elif mint == "pictographs":
                need_mint, quantity = await self.need_mint_and_quantity(
                    contract=pictographs_contract, max_mint=pictographs_max_mint
                )
                if need_mint and quantity:
                    await self.pictographs_mint(contract=pictographs_contract)
                else:
                    continue

            elif mint == "tokentails":
                need_mint, quantity = await self.need_mint_and_quantity(
                    contract=token_tails_contract, max_mint=token_tails_max_mint
                )
                if need_mint and quantity:
                    await self.token_tails_mint(contract=token_tails_contract)
                else:
                    continue

            sleep_time = random.randint(start_delay, end_delay)
            logger.info(f"{self.user} pausing for {sleep_time} seconds before next mint")
            await asyncio.sleep(sleep_time)
        logger.success(f"{self.user} all NFTs minted successfully")
        return True

    async def _check_balance(
        self,
        contract: AsyncContract,
    ):
        module_contract = self.client.w3.eth.contract(
            address=self.client.w3.to_checksum_address(contract.address),
            abi=contract.abi,
        )
        balance = await module_contract.functions.balanceOf(
            self.client.account.address
        ).call()

        return balance

    async def need_mint_and_quantity(self, contract: AsyncContract, max_mint: int = 1):
        settings = Settings()
        multiple_mint = settings.multiple_mint
        balance = await self._check_balance(contract)
        quantity_mint = 0

        if balance > 0 and not multiple_mint:
            return False, quantity_mint
        elif max_mint - balance <= 0:
            return False, quantity_mint
        elif multiple_mint:
            quantity_mint = random.randint(1, max_mint - balance)
            return True, quantity_mint
        else:
            return True, 1

    async def execute_transaction(
        self,
        tx_params: TxParams,
        activity_type: str = "unknown",
        timeout: int = 180,
        retry_count: int = 0,
    ) -> TransactionResult:
        attempt = 0
        last_error = None

        while attempt <= retry_count:
            try:
                logger.info(
                    f"{self.user} Executing {activity_type} transaction {activity_type}"
                    f"{f' (attempt {attempt + 1})' if attempt > 0 else ''}"
                )
                # Отправляем транзакцию
                tx = await self.client.transactions.sign_and_send(tx_params=tx_params)

                # Ждем подтверждения
                receipt = await tx.wait_for_receipt(self.client, timeout=timeout)

                if receipt and tx.params:
                    # Проверяем статус
                    status = receipt.get("status", 1)
                    if status == 0:
                        raise Exception("Transaction reverted")

                    logger.success(
                        f"{self.client.account.address} Transaction confirmed: 0x{tx.hash.hex() if tx.hash else 0}"
                    )

                    return TransactionResult(
                        success=True,
                        tx_hash=tx.hash.hex() if tx.hash else "0",
                        receipt=receipt,
                    )
                else:
                    raise Exception("Transaction receipt timeout")

            except Exception as e:
                last_error = str(e)
                logger.error(f"Transaction failed on attempt {attempt + 1}: {e}")

                # Проверяем специфичные ошибки
                if "insufficient funds" in str(e).lower():
                    # Не имеет смысла повторять
                    break
                if attempt < retry_count:
                    # Ждем перед повтором
                    await asyncio.sleep(5 * (attempt + 1))

                attempt += 1

        return TransactionResult(
            success=False,
            error_message=last_error or "Unknown error",
        )

    async def base_camp_mint(self, contract: AsyncContract, quantity: int = 1):
        price_per_token = int(MAX_INT, 16)  # Преобразуем MAX_INT в int
        allowlist_proof_params = TxArgs(
            proof=[],
            quantityLimitPerWallet=0,
            pricePerToken=price_per_token,
            currency=ZERO_ADDRESS,
        )
        swap_params = TxArgs(
            _receiver=self.client.account.address,
            _quantity=quantity,
            _currency=ETH_ADDRESS,
            _pricePerToken=0,
            _allowlistProof=allowlist_proof_params.tuple(),
            _data="0x",
        )

        # Получаем контракт и кодируем данные
        data = contract.encode_abi("claim", args=(swap_params.tuple()))

        tx_params = TxParams(to=contract.address, data=data)

        # Выполняем через TransactionExecutor
        result = await self.execute_transaction(
            tx_params=tx_params, activity_type="Base_camp_mint", retry_count=3
        )

        if result.success:
            return result.tx_hash
        else:
            raise Exception(f"Mint failed: {result.error_message}")

    async def aura_mint(self, contract: AsyncContract, quantity: int = 1):
        price_per_token = int(MAX_INT, 16)  # Преобразуем MAX_INT в int
        allowlist_proof_params = TxArgs(
            proof=[],
            quantityLimitPerWallet=0,
            pricePerToken=price_per_token,
            currency=ZERO_ADDRESS,
        )
        swap_params = TxArgs(
            _receiver=self.client.account.address,
            _quantity=quantity,
            _currency=ETH_ADDRESS,
            _pricePerToken=0,
            _allowlistProof=allowlist_proof_params.tuple(),
            _data="0x",
        )

        # Получаем контракт и кодируем данные
        data = contract.encode_abi("claim", args=(swap_params.tuple()))

        tx_params = TxParams(to=contract.address, data=data)

        # Выполняем через TransactionExecutor
        result = await self.execute_transaction(
            tx_params=tx_params, activity_type="Aura_mint", retry_count=3
        )

        if result.success:
            return result.tx_hash
        else:
            raise Exception(f"Mint failed: {result.error_message}")

    async def sticky_pleb_mint(self, contract: AsyncContract, quantity: int = 1):
        allowlist_proof_params = TxArgs(
            proof=[
                "0x0000000000000000000000000000000000000000000000000000000000000000"
            ],
            quantityLimitPerWallet=1,
            pricePerToken=0,
            currency=ETH_ADDRESS,
        )
        swap_params = TxArgs(
            _receiver=self.client.account.address,
            _quantity=quantity,
            _currency=ETH_ADDRESS,
            _pricePerToken=0,
            _allowlistProof=allowlist_proof_params.tuple(),
            _data="0x",
        )

        # Получаем контракт и кодируем данные
        data = contract.encode_abi("claim", args=(swap_params.tuple()))

        tx_params = TxParams(to=contract.address, data=data)

        # Выполняем через TransactionExecutor
        result = await self.execute_transaction(
            tx_params=tx_params, activity_type="Sticky_pleb_mint", retry_count=3
        )

        if result.success:
            return result.tx_hash
        else:
            raise Exception(f"Mint failed: {result.error_message}")

    async def climb_mint(self, contract: AsyncContract, quantity: int = 1):
        price_per_token = int(MAX_INT, 16)  # Преобразуем MAX_INT в int
        allowlist_proof_params = TxArgs(
            proof=[],
            quantityLimitPerWallet=0,
            pricePerToken=price_per_token,
            currency=ZERO_ADDRESS,
        )
        real_price_per_token = 1000000000000000
        swap_params = TxArgs(
            _receiver=self.client.account.address,
            _quantity=quantity,
            _currency=ETH_ADDRESS,
            _pricePerToken=real_price_per_token,
            _allowlistProof=allowlist_proof_params.tuple(),
            _data="0x",
        )

        value = real_price_per_token * quantity
        value = TokenAmount(value, wei=True).Wei
        # Получаем контракт и кодируем данные
        data = contract.encode_abi("claim", args=(swap_params.tuple()))

        tx_params = TxParams(to=contract.address, data=data, value=value)

        # Выполняем через TransactionExecutor
        result = await self.execute_transaction(
            tx_params=tx_params, activity_type="climb_mint", retry_count=3
        )

        if result.success:
            return result.tx_hash
        else:
            raise Exception(f"Mint failed: {result.error_message}")

    async def pictographs_mint(self, contract: AsyncContract):
        # Получаем контракт и кодируем данные
        data = "0x14f710fe"

        tx_params = TxParams(to=contract.address, data=data)

        # Выполняем через TransactionExecutor
        result = await self.execute_transaction(
            tx_params=tx_params, activity_type="pictographs_mint", retry_count=3
        )

        if result.success:
            return result.tx_hash
        else:
            raise Exception(f"Mint failed: {result.error_message}")

    async def token_tails_mint(self, contract: AsyncContract):
        swap_params = TxArgs(
            to=self.client.account.address,
        )

        data = contract.encode_abi("safeMint", args=(swap_params.tuple()))

        tx_params = TxParams(to=contract.address, data=data)

        # Выполняем через TransactionExecutor
        result = await self.execute_transaction(
            tx_params=tx_params, activity_type="token_tails_mint", retry_count=3
        )

        if result.success:
            return result.tx_hash
        else:
            raise Exception(f"Mint failed: {result.error_message}")

    async def omnihub_mint(self, contract: AsyncContract | Contract):
        # Get contract and encode data
        data = "0xa25ffea800000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000800000000000000000000000000000000000000000000000000000000000000000"

        tx_params = TxParams(to=contract.address, data=data, value=TokenAmount(amount=100000000000000, wei=True).Wei)

        # Execute via TransactionExecutor
        result = await self.execute_transaction(
            tx_params=tx_params, activity_type="omnihub_mint", retry_count=3
        )

        if result.success:
            return result.tx_hash
        else:
            raise Exception(f"Mint failed: {result.error_message}")

    async def tavern_quest_mint(self, contract: AsyncContract | Contract):
        # Get contract and encode data
        data = "0xba41b0c6000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000000000000000000"

        tx_params = TxParams(to=contract.address, data=data)

        # Execute via TransactionExecutor
        result = await self.execute_transaction(
            tx_params=tx_params, activity_type="tavern_quest_mint", retry_count=3
        )

        if result.success:
            return result.tx_hash
        else:
            raise Exception(f"Mint failed: {result.error_message}")

    async def mintpad_mint(self, contract: AsyncContract | Contract):
        # Get contract and encode data
        data = f"0xb510391f000000000000000000000000ac6f313c90c5a4c38811766ff09b4394921f853800000000000000000000000000000000000000000000000000000000000000400000000000000000000000000000000000000000000000000000000000000044449a52f8000000000000000000000000{self.client.account.address[2:]}000000000000000000000000000000000000000000000000000000000000000100000000000000000000000000000000000000000000000000000000"

        tx_params = TxParams(to=contract.address, data=data, value=TokenAmount(amount=6660000000, wei=True).Wei)

        # Execute via TransactionExecutor
        result = await self.execute_transaction(
            tx_params=tx_params, activity_type="mintpad_mint", retry_count=3
        )

        if result.success:
            return result.tx_hash
        else:
            raise Exception(f"Mint failed: {result.error_message}")
