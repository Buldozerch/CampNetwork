from typing import Dict, Any, Optional

class WalletException(Exception):
    pass

class Web3AsyncException(Exception):
    """Base exception for all eth_async exceptions."""
    pass


class WrongChainID(Web3AsyncException):
    """Исключение для неверного Chain ID."""
    pass


class WrongCoinSymbol(Web3AsyncException):
    """Исключение для неверного символа монеты."""
    pass


class ClientException(Web3AsyncException):
    """Базовое исключение для ошибок клиента."""
    pass


class InvalidProxy(ClientException):
    """Исключение для неверного прокси."""
    pass


class TransactionException(Web3AsyncException):
    """Базовое исключение для ошибок транзакций."""
    pass


class GasPriceTooHigh(TransactionException):
    """Исключение при слишком высокой цене газа."""
    pass


class TransactionReverted(TransactionException):
    """Исключение при отмене транзакции."""
    def __init__(self, message: str = None, receipt: Dict[str, Any] = None):
        self.receipt = receipt
        super().__init__(message or "Transaction reverted")


class TransactionNotConfirmed(TransactionException):
    """Исключение при неподтвержденной транзакции."""
    pass


class InsufficientFunds(TransactionException):
    """Исключение при недостаточном балансе."""
    pass


class APIException(Web3AsyncException):
    """Базовое исключение для ошибок API."""
    pass


class ContractException(Web3AsyncException):
    """Исключение для ошибок контракта."""
    pass


class MethodNotSupported(Web3AsyncException):
    """Исключение для неподдерживаемых методов."""
    pass


class HTTPException(Web3AsyncException):
    """
    Исключение при неудачном HTTP-запросе.

    Attributes:
        response (Optional[Dict[str, Any]]): JSON-ответ на запрос
        status_code (Optional[int]): Код статуса запроса
    """
    response: Optional[Dict[str, Any]]
    status_code: Optional[int]

    def __init__(self, response: Optional[Dict[str, Any]] = None, status_code: Optional[int] = None) -> None:
        """
        Инициализирует класс.

        Args:
            response (Optional[Dict[str, Any]]): JSON-ответ на запрос (None)
            status_code (Optional[int]): Код статуса запроса (None)
        """
        self.response = response
        self.status_code = status_code
        message = f"HTTP Error"
        if status_code:
            message += f" {status_code}"
        if response:
            message += f": {response}"
        super().__init__(message)
