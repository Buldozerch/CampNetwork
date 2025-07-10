from typing import Union, TypedDict, Optional
from web3 import types
from web3.contract import AsyncContract

from libs.eth_async.data.models import RawContract, TokenAmount

# Типы для контрактов
Contract = Union[str, types.Address, types.ChecksumAddress, types.ENS, RawContract, AsyncContract]
Address = Union[str, types.Address, types.ChecksumAddress, types.ENS]
Amount = Union[float, int, TokenAmount]
GasPrice = Union[int, TokenAmount]
GasLimit = Union[int, TokenAmount]


class TxParams(TypedDict, total=False):
    """Типизированный словарь для параметров транзакции"""
    from_: Optional[str]  # Поле from зарезервировано в Python
    to: Optional[str]
    gas: Optional[int]
    gasPrice: Optional[int]
    maxFeePerGas: Optional[int]
    maxPriorityFeePerGas: Optional[int]
    value: Optional[int]
    data: Optional[str]
    nonce: Optional[int]
    chainId: Optional[int]
