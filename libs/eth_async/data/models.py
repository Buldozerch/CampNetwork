import json
from decimal import Decimal
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Union

import requests
from web3 import AsyncWeb3
from eth_typing import ChecksumAddress

from libs.eth_async import exceptions
from libs.eth_async.data import config
from libs.eth_async.classes import AutoRepr
from libs.eth_async.blockscan_api import APIFunctions


class TokenAmount:
    """
    Класс для работы с количеством токенов.
    """

    Wei: int
    Ether: Decimal
    decimals: int

    def __init__(
        self, amount: int | float | str | Decimal, decimals: int = 18, wei: bool = False
    ) -> None:
        """
        Инициализирует класс TokenAmount.

        Args:
            amount: Количество токенов
            decimals: Количество десятичных знаков токена
            wei: True, если amount указан в wei (минимальных единицах токена)
        """
        if wei:
            self.Wei: int = int(amount)
            self.Ether: Decimal = Decimal(str(amount)) / 10**decimals

        else:
            self.Wei: int = int(Decimal(str(amount)) * 10**decimals)
            self.Ether: Decimal = Decimal(str(amount))

        self.decimals = decimals

    def __str__(self):
        return f"{self.Wei}"

    def __repr__(self):
        return (
            f"TokenAmount(Wei={self.Wei}, Ether={self.Ether}, decimals={self.decimals})"
        )

    def __eq__(self, other):
        if isinstance(other, TokenAmount):
            return self.Wei == other.Wei
        return False

    def __lt__(self, other):
        if isinstance(other, TokenAmount):
            return self.Wei < other.Wei
        return NotImplemented

    def __gt__(self, other):
        if isinstance(other, TokenAmount):
            return self.Wei > other.Wei
        return NotImplemented

    def __le__(self, other):
        if isinstance(other, TokenAmount):
            return self.Wei <= other.Wei
        return NotImplemented

    def __ge__(self, other):
        if isinstance(other, TokenAmount):
            return self.Wei >= other.Wei
        return NotImplemented

    def __add__(self, other):
        if isinstance(other, TokenAmount):
            if self.decimals != other.decimals:
                raise ValueError(
                    f"Cannot add TokenAmount with different decimals: {self.decimals} and {other.decimals}"
                )
            return TokenAmount(
                amount=self.Wei + other.Wei, decimals=self.decimals, wei=True
            )
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, TokenAmount):
            if self.decimals != other.decimals:
                raise ValueError(
                    f"Cannot subtract TokenAmount with different decimals: {self.decimals} and {other.decimals}"
                )
            return TokenAmount(
                amount=self.Wei - other.Wei, decimals=self.decimals, wei=True
            )
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, (int, float, Decimal)):
            return TokenAmount(
                amount=int(self.Wei * other), decimals=self.decimals, wei=True
            )
        return NotImplemented

    def __truediv__(self, other):
        if isinstance(other, (int, float, Decimal)):
            return TokenAmount(
                amount=int(self.Wei / other), decimals=self.decimals, wei=True
            )
        if isinstance(other, TokenAmount):
            if self.decimals != other.decimals:
                raise ValueError(
                    f"Cannot divide TokenAmount with different decimals: {self.decimals} and {other.decimals}"
                )
            return self.Wei / other.Wei
        return NotImplemented


@dataclass
class DefaultABIs:
    """
    Класс с дефолтными ABI для токенов и других контрактов.
    """

    Token = [
        {
            "constant": True,
            "inputs": [],
            "name": "name",
            "outputs": [{"name": "", "type": "string"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "totalSupply",
            "outputs": [{"name": "", "type": "uint256"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint256"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [{"name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [
                {"name": "owner", "type": "address"},
                {"name": "spender", "type": "address"},
            ],
            "name": "allowance",
            "outputs": [{"name": "remaining", "type": "uint256"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": False,
            "inputs": [
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
            ],
            "name": "approve",
            "outputs": [],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "constant": False,
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
            ],
            "name": "transfer",
            "outputs": [],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        },
    ]

    # ABI для NFT (ERC-721)
    NFT = [
        {
            "constant": True,
            "inputs": [{"name": "owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "balance", "type": "uint256"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [{"name": "tokenId", "type": "uint256"}],
            "name": "ownerOf",
            "outputs": [{"name": "owner", "type": "address"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": False,
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "tokenId", "type": "uint256"},
            ],
            "name": "transfer",
            "outputs": [],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "constant": False,
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "tokenId", "type": "uint256"},
            ],
            "name": "safeTransferFrom",
            "outputs": [],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "constant": False,
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "approved", "type": "bool"},
            ],
            "name": "setApprovalForAll",
            "outputs": [],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [
                {"name": "owner", "type": "address"},
                {"name": "operator", "type": "address"},
            ],
            "name": "isApprovedForAll",
            "outputs": [{"name": "approved", "type": "bool"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "name",
            "outputs": [{"name": "", "type": "string"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [],
            "name": "symbol",
            "outputs": [{"name": "", "type": "string"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [{"name": "tokenId", "type": "uint256"}],
            "name": "tokenURI",
            "outputs": [{"name": "", "type": "string"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
    ]


@dataclass
class API:
    """
    Класс с информацией об API блокчейн-сканера.

    Attributes:
        key (str): API ключ.
        url (str): URL входной точки API.
        docs (str): URL документации.
        functions (Optional[APIFunctions]): Инстанс функций API.
    """

    key: str
    url: str
    docs: str | None = None
    functions: APIFunctions | None = None


class Network:
    """
    Класс, представляющий сеть Ethereum.
    """

    def __init__(
        self,
        name: str,
        rpc: str,
        decimals: int | None = None,
        chain_id: int | None = None,
        tx_type: int = 0,
        coin_symbol: str | None = None,
        explorer: str | None = None,
        api: API | None = None,
    ) -> None:
        """
        Инициализирует класс Network.

        Args:
            name: Название сети
            rpc: RPC URL
            decimals: Количество десятичных знаков нативной монеты
            chain_id: Chain ID сети
            tx_type: Тип транзакций (0 - Legacy, 2 - EIP-1559)
            coin_symbol: Символ нативной монеты
            explorer: URL блокчейн-сканера
            api: Инстанс API
        """
        self.name: str = name.lower()
        self.rpc: str = rpc
        self.chain_id: int | None = chain_id
        self.tx_type: int = tx_type
        self.coin_symbol: str | None = coin_symbol
        self.explorer: str | None = explorer
        self.decimals = decimals
        self.api = api

        if not self.chain_id:
            try:
                web3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.rpc))
                self.chain_id = AsyncWeb3.to_sync_loop(web3.eth.chain_id)
            except Exception as err:
                raise exceptions.WrongChainID(f"Can not get chain id: {err}")

        if not self.coin_symbol or not self.decimals:
            try:
                network = None
                networks_info_response = requests.get(
                    "https://chainid.network/chains.json"
                ).json()
                for network_ in networks_info_response:
                    if network_["chainId"] == self.chain_id:
                        network = network_
                        break

                if not self.coin_symbol and network:
                    self.coin_symbol = network["nativeCurrency"]["symbol"]
                if not self.decimals and network:
                    self.decimals = int(network["nativeCurrency"]["decimals"])

            except Exception as err:
                raise exceptions.WrongCoinSymbol(f"Can not get coin symbol: {err}")

        if self.coin_symbol:
            self.coin_symbol = self.coin_symbol.upper()

        self.set_api_functions()

    def set_api_functions(self) -> None:
        """
        Обновляет функции API после изменения API ключа.
        """
        if self.api and self.api.key and self.api.url:
            self.api.functions = APIFunctions(self.api.key, self.api.url)

    def __repr__(self) -> str:
        return f"Network(name='{self.name}', chain_id={self.chain_id})"


class Networks:
    """
    Класс со списком доступных сетей.
    """

    # Mainnets
    Ethereum = Network(
        name="ethereum",
        rpc="https://1rpc.io/eth",
        chain_id=1,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://etherscan.io/",
        api=API(
            key=config.ETHEREUM_API_KEY,
            url="https://api.etherscan.io/api",
            docs="https://docs.etherscan.io/",
        ),
    )

    Arbitrum = Network(
        name="arbitrum",
        rpc="https://1rpc.io/arb",
        chain_id=42161,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://arbiscan.io/",
        api=API(
            key=config.ARBITRUM_API_KEY,
            url="https://api.arbiscan.io/api",
            docs="https://docs.arbiscan.io/",
        ),
    )

    ArbitrumNova = Network(
        name="arbitrum_nova",
        rpc="https://nova.arbitrum.io/rpc/",
        chain_id=42170,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://nova.arbiscan.io/",
        api=API(
            key=config.ARBITRUM_API_KEY,
            url="https://api-nova.arbiscan.io/api",
            docs="https://nova.arbiscan.io/apis/",
        ),
    )

    Optimism = Network(
        name="optimism",
        rpc="https://0xrpc.io/op",
        chain_id=10,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://optimistic.etherscan.io/",
        api=API(
            key=config.OPTIMISM_API_KEY,
            url="https://api-optimistic.etherscan.io/api",
            docs="https://docs.optimism.etherscan.io/",
        ),
    )

    BSC = Network(
        name="bsc",
        rpc="https://1rpc.io/bnb",
        chain_id=56,
        tx_type=0,
        coin_symbol="BNB",
        decimals=18,
        explorer="https://bscscan.com/",
        api=API(
            key=config.BSC_API_KEY,
            url="https://api.bscscan.com/api",
            docs="https://docs.bscscan.com/",
        ),
    )

    Polygon = Network(
        name="polygon",
        rpc="https://1rpc.io/matic",
        chain_id=137,
        tx_type=2,
        coin_symbol="MATIC",
        decimals=18,
        explorer="https://polygonscan.com/",
        api=API(
            key=config.POLYGON_API_KEY,
            url="https://api.polygonscan.com/api",
            docs="https://docs.polygonscan.com/",
        ),
    )

    Avalanche = Network(
        name="avalanche",
        rpc="https://1rpc.io/avax/c",
        chain_id=43114,
        tx_type=2,
        coin_symbol="AVAX",
        decimals=18,
        explorer="https://snowtrace.io/",
        api=API(
            key=config.AVALANCHE_API_KEY,
            url="https://api.snowtrace.io/api",
            docs="https://docs.snowtrace.io/",
        ),
    )

    Moonbeam = Network(
        name="moonbeam",
        rpc="https://rpc.api.moonbeam.network/",
        chain_id=1284,
        tx_type=2,
        coin_symbol="GLMR",
        decimals=18,
        explorer="https://moonscan.io/",
        api=API(
            key=config.MOONBEAM_API_KEY,
            url="https://api-moonbeam.moonscan.io/api",
            docs="https://moonscan.io/apis/",
        ),
    )

    Fantom = Network(
        name="fantom",
        rpc="https://fantom.publicnode.com",
        chain_id=250,
        tx_type=0,
        coin_symbol="FTM",
        decimals=18,
        explorer="https://ftmscan.com/",
        api=API(
            key=config.FANTOM_API_KEY,
            url="https://api.ftmscan.com/api",
            docs="https://docs.ftmscan.com/",
        ),
    )

    Celo = Network(
        name="celo",
        rpc="https://1rpc.io/celo",
        chain_id=42220,
        tx_type=0,
        coin_symbol="CELO",
        decimals=18,
        explorer="https://celoscan.io/",
        api=API(
            key=config.CELO_API_KEY,
            url="https://api.celoscan.io/api",
            docs="https://celoscan.io/apis/",
        ),
    )

    ZkSync = Network(
        name="zksync",
        rpc="https://mainnet.era.zksync.io",
        chain_id=324,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://explorer.zksync.io/",
    )

    Gnosis = Network(
        name="gnosis",
        rpc="https://1rpc.io/gnosis",
        chain_id=100,
        tx_type=2,
        coin_symbol="xDAI",
        decimals=18,
        explorer="https://gnosisscan.io/",
        api=API(
            key=config.GNOSIS_API_KEY,
            url="https://api.gnosisscan.io/api",
            docs="https://docs.gnosisscan.io/",
        ),
    )

    Base = Network(
        name="base",
        rpc="https://0xrpc.io/base",
        chain_id=8453,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://basescan.org/",
        api=API(
            key=config.BASE_API_KEY,
            url="https://api.basescan.org/api",
            docs="https://docs.basescan.org/",
        ),
    )

    Linea = Network(
        name="linea",
        rpc="https://rpc.linea.build",
        chain_id=59144,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://lineascan.build/",
        api=API(
            key=config.LINEA_API_KEY,
            url="https://api.lineascan.build/api",
            docs="https://docs.lineascan.build/",
        ),
    )

    Mode = Network(
        name="mode",
        rpc="https://1rpc.io/mode",
        chain_id=34443,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://modescan.io/",
        api=API(
            key=config.MODE_API_KEY,
            url="https://modescan.io/",
            docs="https://modescan.io/documentation/etherscan-compatibility",
        ),
    )

    Soneium = Network(
        name="soneium",
        rpc="https://rpc.soneium.org",
        chain_id=1868,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://soneium.blockscout.com/",
        api=API(
            key=config.SONEIUM_API_KEY,
            url="https://soneium.blockscout.com/",
            docs="https://soneium.blockscout.com/api-docs",
        ),
    )

    Ink = Network(
        name="ink",
        rpc="https://rpc-qnd.inkonchain.com",
        chain_id=57073,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://explorer.inkonchain.com/",
        api=API(
            key=config.INK_API_KEY,
            url="https://explorer.inkonchain.com/",
            docs="https://explorer.inkonchain.com/api-docs",
        ),
    )

    Unichain = Network(
        name="unichain",
        rpc="https://unichain.drpc.org",
        chain_id=130,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://uniscan.xyz/",
        api=API(
            key=config.UNICHAIN_API_KEY,
            url="https://uniscan.xyz/",
            docs="https://docs.uniscan.xyz/",
        ),
    )

    Lisk = Network(
        name="lisk",
        rpc="https://rpc.api.lisk.com",
        chain_id=1135,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://blockscout.lisk.com/",
        api=API(
            key=config.LISK_API_KEY,
            url="https://blockscout.lisk.com/",
            docs="https://blockscout.lisk.com/api-docs",
        ),
    )

    Camp = Network(
        name="camp",
        rpc="https://rpc.basecamp.t.raas.gelato.cloud",
        chain_id=123420001114,
        tx_type=2,
        coin_symbol="CAMP",
        decimals=18,
        explorer="https://basecamp.cloud.blockscout.com",
        api=API(
            key=config.EXAMPLE_API_KEY,
            url="https://basecamp.cloud.blockscout.com",
            docs="https://basecamp.cloud.blockscout.com",
        ),
    )
    Example = Network(
        name="",
        rpc="",
        chain_id=5,
        tx_type=2,
        coin_symbol="",
        decimals=18,
        explorer="",
        api=API(key=config.EXAMPLE_API_KEY, url="", docs=""),
    )
    # Testnets
    Goerli = Network(
        name="goerli",
        rpc="https://rpc.ankr.com/eth_goerli/",
        chain_id=5,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://goerli.etherscan.io/",
        api=API(
            key=config.GOERLI_API_KEY,
            url="https://api-goerli.etherscan.io/api",
            docs="https://docs.etherscan.io/v/goerli-etherscan/",
        ),
    )

    Sepolia = Network(
        name="sepolia",
        rpc="https://1rpc.io/sepolia",
        chain_id=11155111,
        tx_type=2,
        coin_symbol="ETH",
        decimals=18,
        explorer="https://sepolia.etherscan.io",
        api=API(
            key=config.SEPOLIA_API_KEY,
            url="https://api-sepolia.etherscan.io/api",
            docs="https://docs.etherscan.io/v/sepolia-etherscan/",
        ),
    )


class RawContract(AutoRepr):
    """
    Класс, представляющий сырой контракт.

    Attributes:
        title str: Название контракта.
        address (ChecksumAddress): Адрес контракта.
        abi list[dict[str, Any]] | str: ABI контракта.
    """

    title: str
    address: ChecksumAddress
    abi: list[dict[str, ...]]

    def __init__(
        self,
        address: str,
        abi: list[dict[str, ...]] | str | None = None,
        title: str = "",
    ) -> None:
        """
        Инициализирует класс.

        Args:
            title (str): Название контракта.
            address (str): Адрес контракта.
            abi (Union[List[Dict[str, Any]], str]): ABI контракта.
        """
        self.title = title
        self.address = AsyncWeb3.to_checksum_address(address)
        self.abi = json.loads(abi) if isinstance(abi, str) else abi

    def __eq__(self, other) -> bool:
        if self.address == other.address and self.abi == other.abi:
            return True
        return False


@dataclass
class CommonValues:
    """
    Класс с общими значениями для транзакций.
    """

    Null: str = "0x0000000000000000000000000000000000000000000000000000000000000000"
    InfinityStr: str = (
        "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    )
    InfinityInt: int = int(
        "0xffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", 16
    )
    ZeroAddress: str = "0x0000000000000000000000000000000000000000"


class TxArgs(AutoRepr):
    """
    Класс для именованных аргументов транзакции.
    """

    def __init__(self, **kwargs) -> None:
        """
        Инициализирует класс.

        Args:
            **kwargs: Именованные аргументы транзакции контракта.
        """
        self.__dict__.update(kwargs)

    def list(self) -> list[...]:
        """
        Получает список аргументов транзакции.

        Returns:
            List[Any]: Список аргументов транзакции.
        """
        return list(self.__dict__.values())

    def tuple(self) -> tuple[str, ...]:
        """
        Получает кортеж аргументов транзакции.

        Returns:
            Tuple[Any]: Кортеж аргументов транзакции.
        """
        return tuple(self.__dict__.values())
