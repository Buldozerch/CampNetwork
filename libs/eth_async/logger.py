import logging
import time
import functools
from typing import Any, Callable, Optional, TypeVar, cast

T = TypeVar('T')


class EthLogger:
    """
    Логгер для библиотеки eth_async.
    """
    
    def __init__(self, level=logging.INFO, name="eth_async"):
        """
        Инициализирует логгер.
        
        Args:
            level: Уровень логирования
            name: Имя логгера
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            
    def debug(self, message: str) -> None:
        """
        Логирует сообщение с уровнем DEBUG.
        
        Args:
            message: Сообщение для логирования
        """
        self.logger.debug(message)
        
    def info(self, message: str) -> None:
        """
        Логирует сообщение с уровнем INFO.
        
        Args:
            message: Сообщение для логирования
        """
        self.logger.info(message)
        
    def warning(self, message: str) -> None:
        """
        Логирует сообщение с уровнем WARNING.
        
        Args:
            message: Сообщение для логирования
        """
        self.logger.warning(message)
        
    def error(self, message: str) -> None:
        """
        Логирует сообщение с уровнем ERROR.
        
        Args:
            message: Сообщение для логирования
        """
        self.logger.error(message)
        
    def critical(self, message: str) -> None:
        """
        Логирует сообщение с уровнем CRITICAL.
        
        Args:
            message: Сообщение для логирования
        """
        self.logger.critical(message)
            
    def log_transaction(self, tx_hash: str, tx_params: Optional[dict] = None, status: str = "SENT") -> None:
        """
        Логирует информацию о транзакции.
        
        Args:
            tx_hash: Хеш транзакции
            tx_params: Параметры транзакции
            status: Статус транзакции
        """
        self.logger.info(f"Transaction {status}: {tx_hash}")
        if tx_params:
            self.logger.debug(f"Transaction params: {tx_params}")
        
    def log_contract_call(self, contract_address: str, method: str, args: Optional[Any] = None, result: Optional[Any] = None) -> None:
        """
        Логирует вызов контракта.
        
        Args:
            contract_address: Адрес контракта
            method: Метод контракта
            args: Аргументы метода
            result: Результат вызова
        """
        self.logger.info(f"Contract call: {contract_address}.{method}")
        if args:
            self.logger.debug(f"Args: {args}")
        if result is not None:
            self.logger.debug(f"Result: {result}")
            
    def timing_decorator(self, func: Optional[Callable[..., T]] = None, name: Optional[str] = None) -> Callable[..., T]:
        """
        Декоратор для измерения времени выполнения функции.
        
        Args:
            func: Функция для декорирования
            name: Имя для логирования
            
        Returns:
            Callable: Декорированная функция
        """
        def decorator(f: Callable[..., T]) -> Callable[..., T]:
            @functools.wraps(f)
            async def wrapped(*args: Any, **kwargs: Any) -> T:
                start_time = time.time()
                try:
                    result = await f(*args, **kwargs)
                    elapsed = time.time() - start_time
                    self.logger.debug(f"{name or f.__name__} completed in {elapsed:.4f}s")
                    return result
                except Exception as e:
                    elapsed = time.time() - start_time
                    self.logger.error(f"{name or f.__name__} failed after {elapsed:.4f}s: {str(e)}")
                    raise
            return wrapped
        
        if func:
            return decorator(func)
        return decorator
