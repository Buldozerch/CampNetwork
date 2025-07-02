import os
import random
from typing import List, Tuple, Optional
from loguru import logger
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB
from data import config


class ResourceManager:
    """Класс для управления ресурсами (прокси, токены Twitter)"""

    def __init__(self):
        """Инициализация менеджера ресурсов"""
        pass

    def _load_from_file(self, file_path: str) -> List[str]:
        """
        Загружает данные из файла

        Args:
            file_path: Путь к файлу

        Returns:
            Список строк из файла
        """
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            with open(file_path, "r") as file:
                return [line.strip() for line in file if line.strip()]
        return []

    def _save_to_file(self, file_path: str, data: List[str]) -> bool:
        """
        Сохраняет данные в файл

        Args:
            file_path: Путь к файлу
            data: Список строк для сохранения

        Returns:
            Статус успеха
        """
        try:
            with open(file_path, "w") as file:
                for line in data:
                    file.write(f"{line}\n")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении в файл {file_path}: {str(e)}")
            return False

    def _get_available_proxy(self) -> Optional[str]:
        """
        Получает доступное резервное прокси и удаляет его из файла

        Returns:
            Прокси или None, если нет доступных
        """
        # Загружаем список прокси из файла
        all_proxies = self._load_from_file(config.RESERVE_PROXY_FILE)

        if not all_proxies:
            logger.warning("Нет доступных прокси в файле")
            return None

        # Выбираем случайное прокси
        proxy = random.choice(all_proxies)

        # Удаляем выбранное прокси из списка
        all_proxies.remove(proxy)

        # Сохраняем обновленный список обратно в файл
        if self._save_to_file(config.RESERVE_PROXY_FILE, all_proxies):
            logger.info(
                f"Прокси успешно выбрано и удалено из файла. Осталось: {len(all_proxies)}"
            )
        else:
            logger.warning(f"Не удалось обновить файл прокси, но прокси было выбрано")

        return proxy

    def _get_available_twitter(self) -> Optional[str]:
        """
        Получает доступный резервный токен Twitter и удаляет его из файла

        Returns:
            Токен или None, если нет доступных
        """
        # Загружаем список токенов из файла
        all_tokens = self._load_from_file(config.RESERVE_TWITTER_FILE)

        if not all_tokens:
            logger.warning("Нет доступных токенов Twitter в файле")
            return None

        # Выбираем случайный токен
        token = random.choice(all_tokens)

        # Удаляем выбранный токен из списка
        all_tokens.remove(token)

        # Сохраняем обновленный список обратно в файл
        if self._save_to_file(config.RESERVE_TWITTER_FILE, all_tokens):
            logger.info(
                f"Токен Twitter успешно выбран и удален из файла. Осталось: {len(all_tokens)}"
            )
        else:
            logger.warning(
                f"Не удалось обновить файл токенов Twitter, но токен был выбран"
            )

        return token

    async def get_bad_resources_stats(self) -> Tuple[int, int]:
        """
        Получает статистику плохих ресурсов

        Returns:
            (bad_proxies, bad_twitter): Количество плохих ресурсов
        """
        async with Session() as session:
            db = DB(session)
            return await db.get_bad_resources_count()

    async def replace_proxy(self, user_id: int) -> Tuple[bool, str]:
        """
        Заменяет прокси пользователя

        Args:
            user_id: ID пользователя

        Returns:
            (success, message): Статус успеха и сообщение
        """
        new_proxy = self._get_available_proxy()
        if not new_proxy:
            return False, "Нет доступных резервных прокси"

        async with Session() as session:
            db = DB(session)
            success = await db.replace_bad_proxy(user_id, new_proxy)

            if success:
                return True, f"Прокси успешно заменено на {new_proxy}"
            else:
                # Не возвращаем прокси в файл, так как оно может быть уже использовано
                return False, "Не удалось заменить прокси"

    async def replace_twitter(self, user_id: int) -> Tuple[bool, str]:
        """
        Заменяет токен Twitter пользователя

        Args:
            user_id: ID пользователя

        Returns:
            (success, message): Статус успеха и сообщение
        """
        new_token = self._get_available_twitter()
        if not new_token:
            return False, "Нет доступных резервных токенов Twitter"

        async with Session() as session:
            db = DB(session)
            success = await db.replace_bad_twitter(user_id, new_token)

            if success:
                logger.success(
                    f"Токен Twitter успешно заменен в базе данных для пользователя {user_id}"
                )
                return True, "Токен Twitter успешно заменен"
            else:
                # Не возвращаем токен в файл, так как он может быть уже использован
                logger.error(
                    f"Не удалось заменить токен Twitter в базе данных для пользователя {user_id}"
                )
                return False, "Не удалось заменить токен Twitter"

    async def mark_proxy_as_bad(self, user_id: int) -> bool:
        """
        Отмечает прокси пользователя как плохое

        Args:
            user_id: ID пользователя

        Returns:
            Статус успеха
        """
        async with Session() as session:
            db = DB(session)
            return await db.mark_proxy_as_bad(user_id)

    async def mark_twitter_as_bad(self, user_id: int) -> bool:
        """
        Отмечает токен Twitter пользователя как плохой

        Args:
            user_id: ID пользователя

        Returns:
            Статус успеха
        """
        async with Session() as session:
            db = DB(session)
            return await db.mark_twitter_as_bad(user_id)

    async def mark_wallet_as_blocked(self, user_id: int) -> bool:
        async with Session() as session:
            db = DB(session)
            return await db.mark_account_as_blocked(user_id)

    async def get_bad_proxies(self) -> List:
        """
        Получает список кошельков с плохими прокси

        Returns:
            Список кошельков
        """
        async with Session() as session:
            db = DB(session)
            return await db.get_wallets_with_bad_proxy()

    async def get_bad_twitter(self) -> List:
        """
        Получает список кошельков с плохими токенами Twitter

        Returns:
            Список кошельков
        """
        async with Session() as session:
            db = DB(session)
            return await db.get_wallets_with_bad_twitter()

    async def replace_all_bad_proxies(self) -> Tuple[int, int]:
        """
        Заменяет все плохие прокси

        Returns:
            (replaced, total): Количество замененных прокси и общее количество плохих прокси
        """
        replaced = 0

        async with Session() as session:
            db = DB(session)
            bad_proxies = await db.get_wallets_with_bad_proxy()

            for wallet in bad_proxies:
                success, _ = await self.replace_proxy(wallet.id)
                if success:
                    replaced += 1

            return replaced, len(bad_proxies)

    async def replace_all_bad_twitter(self) -> Tuple[int, int]:
        """
        Заменяет все плохие токены Twitter

        Returns:
            (replaced, total): Количество замененных токенов и общее количество плохих токенов
        """
        replaced = 0

        async with Session() as session:
            db = DB(session)
            bad_twitter = await db.get_wallets_with_bad_twitter()

            for wallet in bad_twitter:
                success, _ = await self.replace_twitter(wallet.id)
                if success:
                    replaced += 1

            return replaced, len(bad_twitter)
