from typing import Dict, Any, Optional, Union
import asyncio
import aiohttp

from libs.eth_async.exceptions import HTTPException, Web3AsyncException
from libs.eth_async.logger import EthLogger

logger = EthLogger()


def aiohttp_params(params: Dict[str, Any] | None) -> Dict[str, Union[str, int, float]] | None:
    """
    Преобразует параметры запроса для aiohttp.

    Args:
        params (Optional[Dict[str, Any]]): Параметры запроса.

    Returns:
        Optional[Dict[str, Union[str, int, float]]]: Параметры для aiohttp.
    """
    if not params:
        return None
        
    new_params = {}
    for key, value in params.items():
        if value is None:
            continue

        if isinstance(value, bool):
            new_params[key] = str(value).lower()
        elif isinstance(value, bytes):
            new_params[key] = value.decode('utf-8')
        else:
            new_params[key] = value

    return new_params


class AsyncSession:
    """
    Класс для работы с асинхронными HTTP-сессиями.
    """
    _session: Optional[aiohttp.ClientSession] = None
    _lock = asyncio.Lock()
    
    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        """
        Возвращает существующую или создает новую сессию.
        
        Returns:
            aiohttp.ClientSession: Сессия aiohttp
        """
        async with cls._lock:
            if cls._session is None or cls._session.closed:
                cls._session = aiohttp.ClientSession()
        return cls._session
        
    @classmethod
    async def close_session(cls) -> None:
        """
        Закрывает сессию если она открыта.
        """
        async with cls._lock:
            if cls._session and not cls._session.closed:
                await cls._session.close()
                cls._session = None
    
    def __init__(self):
        """
        Инициализирует класс.
        """
        self.logger = logger
    
    async def __aenter__(self) -> 'AsyncSession':
        """
        Контекстный менеджер - вход.
        
        Returns:
            AsyncSession: Сессия
        """
        return self
        
    async def __aexit__(self, exc_type, exc, tb) -> None:
        """
        Контекстный менеджер - выход.
        """
        # Не закрываем сессию, так как она переиспользуется
        pass
        
    async def get(
        self, 
        url: str, 
        headers: Dict[str, Any] = None, 
        params: Dict[str, Any] = None,
        timeout: float = 30.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Выполняет GET-запрос и проверяет, был ли он успешным.
        
        Args:
            url (str): URL для запроса.
            headers (Optional[Dict[str, Any]]): Заголовки запроса. (None)
            params (Optional[Dict[str, Any]]): Параметры запроса. (None)
            timeout (float): Таймаут запроса в секундах. (30.0)
            **kwargs: Дополнительные аргументы для запроса.
            
        Returns:
            Dict[str, Any]: Полученный в ответе словарь.
            
        Raises:
            HTTPException: Если запрос неудачен.
        """
        session = await self.get_session()
        try:
            async with session.get(
                url=url,
                headers=headers,
                params=aiohttp_params(params),
                timeout=timeout,
                **kwargs
            ) as response:
                status_code = response.status
                response_json = await response.json()
                
                if status_code <= 201:
                    return response_json
                    
                raise HTTPException(response=response_json, status_code=status_code)
                
        except aiohttp.ClientError as e:
            self.logger.error(f"HTTP request error: {str(e)}")
            raise HTTPException(response={"error": str(e)}, status_code=None)
        
    async def post(
        self, 
        url: str, 
        headers: Dict[str, Any] = None, 
        json: Dict[str, Any] = None,
        data: Any = None,
        timeout: float = 30.0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Выполняет POST-запрос и проверяет, был ли он успешным.
        
        Args:
            url (str): URL для запроса.
            headers (Optional[Dict[str, Any]]): Заголовки запроса. (None)
            json (Optional[Dict[str, Any]]): JSON данные для запроса. (None)
            data (Optional[Any]): Данные для запроса. (None)
            timeout (float): Таймаут запроса в секундах. (30.0)
            **kwargs: Дополнительные аргументы для запроса.
            
        Returns:
            Dict[str, Any]: Полученный в ответе словарь.
            
        Raises:
            HTTPException: Если запрос неудачен.
        """
        session = await self.get_session()
        try:
            async with session.post(
                url=url,
                headers=headers,
                json=json,
                data=data,
                timeout=timeout,
                **kwargs
            ) as response:
                status_code = response.status
                response_json = await response.json()
                
                if status_code <= 201:
                    return response_json
                    
                raise HTTPException(response=response_json, status_code=status_code)
                
        except aiohttp.ClientError as e:
            self.logger.error(f"HTTP request error: {str(e)}")
            raise HTTPException(response={"error": str(e)}, status_code=None)


async def async_get(url: str, headers: Dict[str, Any] = None, **kwargs) -> Dict[str, Any]:
    """
    Выполняет GET-запрос и проверяет, был ли он успешным.

    Args:
        url (str): URL для запроса.
        headers (Optional[Dict[str, Any]]): Заголовки запроса. (None)
        **kwargs: Аргументы для запроса, например, 'params', 'headers', 'data' или 'json'.

    Returns:
        Dict[str, Any]: Полученный в ответе словарь.

    Raises:
        HTTPException: Если запрос неудачен.
    """
    async with AsyncSession() as session:
        return await session.get(url=url, headers=headers, **kwargs)
