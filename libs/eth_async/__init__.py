from typing import Optional

from libs.eth_async.client import Client
from libs.eth_async.data.models import Networks, TokenAmount
from libs.eth_async.exceptions import Web3AsyncException, TransactionException, APIException
from libs.eth_async.logger import EthLogger

__version__ = "2.0.0"

logger = EthLogger()

def create_client(
    private_key: Optional[str] = None,
    network: str = "ethereum",
    proxy: Optional[str] = None,
    check_proxy: bool = False
) -> Client:
    """
    Создает новый клиент eth_async.
    
    Args:
        private_key: Приватный ключ (опционально)
        network: Название сети (ethereum, arbitrum, bsc и т.д.)
        proxy: Прокси (опционально)
        check_proxy: Проверять ли работоспособность прокси
        
    Returns:
        Client: Инстанс клиента
    """
    # Получаем сеть по названию
    network_obj = getattr(Networks, network.capitalize(), None)
    if not network_obj:
        networks = [n for n in dir(Networks) if not n.startswith('_') and n != 'Network']
        raise ValueError(f"Network '{network}' not found. Available networks: {', '.join(networks)}")
        
    return Client(
        private_key=private_key,
        network=network_obj,
        proxy=proxy,
        check_proxy=check_proxy
    )
