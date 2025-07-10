import random
import functools
from decimal import Decimal
from typing import Callable, Any, Dict, List, Optional, Union, TypeVar, cast

from libs.eth_async.exceptions import Web3AsyncException

T = TypeVar('T')
U = TypeVar('U')


def randfloat(from_: int | float | str, to_: int | float | str,
              step: int | float | str | None = None) -> float:
    """
    Возвращает случайное число с плавающей точкой из диапазона.

    Args:
        from_ (Union[int, float, str]): Минимальное значение
        to_ (Union[int, float, str]): Максимальное значение
        step (Optional[Union[int, float, str]]): Размер шага (рассчитывается на основе количества десятичных знаков)
        
    Returns:
        float: Случайное число с плавающей точкой
    """
    from_ = Decimal(str(from_))
    to_ = Decimal(str(to_))
    if not step:
        step = 1 / 10 ** (min(from_.as_tuple().exponent, to_.as_tuple().exponent) * -1)

    step = Decimal(str(step))
    rand_int = Decimal(str(random.randint(0, int((to_ - from_) / step))))
    return float(rand_int * step + from_)


def update_dict(modifiable: Dict[str, Any], template: Dict[str, Any], 
                rearrange: bool = True, remove_extra_keys: bool = False) -> Dict[str, Any]:
    """
    Обновляет указанный словарь с любым количеством словарных вложений на основе шаблона без изменения уже установленных значений.

    Args:
        modifiable (Dict[str, Any]): Словарь для модификации на основе шаблона
        template (Dict[str, Any]): Словарь-шаблон
        rearrange (bool): Сделать порядок ключей как в шаблоне и поместить лишние ключи в конец (True)
        remove_extra_keys (bool): Удалять ли ненужные ключи и их значения (False)
        
    Returns:
        Dict[str, Any]: Модифицированный словарь
    """
    for key, value in template.items():
        if key not in modifiable:
            modifiable.update({key: value})

        elif isinstance(value, dict):
            modifiable[key] = update_dict(
                modifiable=modifiable[key], template=value, rearrange=rearrange, remove_extra_keys=remove_extra_keys
            )

    if rearrange:
        new_dict = {}
        for key in template.keys():
            new_dict[key] = modifiable[key]

        for key in tuple(set(modifiable) - set(new_dict)):
            new_dict[key] = modifiable[key]

    else:
        new_dict = modifiable.copy()

    if remove_extra_keys:
        for key in tuple(set(modifiable) - set(template)):
            del new_dict[key]

    return new_dict


def api_key_required(func: Callable[..., T]) -> Callable[..., T]:
    """
    Проверяет, указан ли API ключ для Blockscan.
    
    Args:
        func: Функция для декорирования
        
    Returns:
        Callable: Декорированная функция
        
    Raises:
        APIException: Если API ключ не указан
    """
    from libs.eth_async.exceptions import APIException
    
    @functools.wraps(func)
    def func_wrapper(self, *args, **kwargs):
        if not self.client.network.api.key or not self.client.network.api.functions:
            raise APIException('To use this function, you must specify the explorer API key!')

        else:
            return func(self, *args, **kwargs)

    return func_wrapper


def parse_proxy(proxy: str) -> Optional[str]:
    """
    Парсит строку прокси в правильный формат.
    
    Args:
        proxy: Строка прокси
        
    Returns:
        Optional[str]: Отформатированная строка прокси или None, если формат неверный
    """
    if proxy.startswith('http'):
        return proxy
    elif "@" in proxy and not proxy.startswith('http'):
        return "http://" + proxy
    else:
        value = proxy.split(':')
        if len(value) == 4:
            ip, port, login, password = value
            return f'http://{login}:{password}@{ip}:{port}'
        else:
            print(f"Invalid proxy format: {proxy}")
            return None  # Вернем None, если формат прокси неправильный


def retry(exceptions: tuple, tries: int = 3, delay: float = 1.0, backoff: float = 2.0) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Декоратор для повторных попыток выполнения функции при возникновении исключений с экспоненциальной задержкой.
    
    Args:
        exceptions: Кортеж исключений, при которых нужно повторить попытку
        tries: Количество попыток
        delay: Начальная задержка между попытками в секундах
        backoff: Множитель для увеличения задержки с каждой попыткой
        
    Returns:
        Callable: Декорированная функция
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            mtries, mdelay = tries, delay
            while mtries > 1:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    # Получаем логгер от первого аргумента (self)
                    logger = getattr(args[0], 'logger', None)
                    if logger:
                        logger.warning(f"Retrying {func.__name__} in {mdelay} seconds after error: {str(e)}")
                    else:
                        print(f"Retrying {func.__name__} in {mdelay} seconds after error: {str(e)}")
                        
                    await asyncio.sleep(mdelay)
                    mtries -= 1
                    mdelay *= backoff
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def async_handle_errors(func: Callable[..., T]) -> Callable[..., T]:
    """
    Декоратор для обработки ошибок в асинхронных функциях.
    
    Args:
        func: Функция для декорирования
        
    Returns:
        Callable: Декорированная функция
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await func(*args, **kwargs)
        except Web3AsyncException as e:
            # Получаем логгер от первого аргумента (self)
            logger = getattr(args[0], 'logger', None)
            if logger:
                logger.error(f"Error in {func.__name__}: {str(e)}")
            else:
                print(f"Error in {func.__name__}: {str(e)}")
            raise
        except Exception as e:
            # Получаем логгер от первого аргумента (self)
            logger = getattr(args[0], 'logger', None)
            if logger:
                logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
            else:
                print(f"Unexpected error in {func.__name__}: {str(e)}")
            raise Web3AsyncException(f"Unexpected error in {func.__name__}: {str(e)}")
    return wrapper

def parse_params(params: str, has_function: bool = True):
    if has_function:
        function_signature = params[:10]
        print('function_signature', function_signature)
        params = params[10:]
    while params:
        print(params[:64])
        params = params[64:]
