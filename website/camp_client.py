from typing import Dict, List, Optional, Any
import random
from loguru import logger
from utils.db_api_async.models import User
from libs.eth_async.client import Client
from libs.eth_async.data.models import Networks
from website.referral_manager import load_ref_codes, get_referral_code_for_registration
from data.models import Settings
from .auth_client import AuthClient
from .quest_client import QuestClient


class CampNetworkClient:
    """Основной клиент для CampNetwork, объединяющий авторизацию и работу с заданиями"""

    def __init__(self, user: User, client: Optional[Client] = None):
        """
        Инициализация клиента CampNetwork

        Args:
            user: Объект пользователя
            client: Клиент блокчейна (опционально)
        """
        self.user = user

        # Создаем клиенты для авторизации и работы с заданиями
        self.auth_client = AuthClient(user=user)
        self.quest_client = QuestClient(user=user)

        # ID заданий для удобного доступа
        self.QUEST_IDS = self.quest_client.QUEST_IDS

    async def login(self, use_referral: bool = True):
        """
        Выполняет авторизацию на сайте с использованием реферального кода при необходимости

        Args:
            use_referral: Использовать ли реферальный код при авторизации

        Returns:
            Статус успеха
        """
        referral_code = None

        # Получаем настройки для реферальных кодов
        settings = Settings()
        use_random_from_db, use_only_file_codes = settings.get_referral_settings()

        # Если нужно использовать реферальный код
        if use_referral and not self.user.completed_quests:
            # Если указано использовать только коды из файла
            if use_only_file_codes:
                file_codes = load_ref_codes()
                referral_code = random.choice(file_codes) if file_codes else None
            else:
                # Используем стандартную логику выбора кода
                referral_code = await get_referral_code_for_registration(
                    use_random_from_db=use_random_from_db
                )

        # Выполняем авторизацию с реферальным кодом

        success, response = await self.auth_client.login_with_referral(
            referral_code=referral_code
        )

        if success:
            # Если авторизация успешна, передаем куки и ID пользователя клиенту заданий
            self.quest_client.cookies = self.auth_client.cookies
            self.quest_client.set_user_id(self.auth_client.user_id)
            return True, response
        else:
            return False, response

    async def complete_all_quests(
        self, retry_failed: bool = True, max_retries: int = 3
    ) -> Dict[str, bool]:
        """
        Выполняет все незавершенные задания с обработкой ошибок

        Args:
            retry_failed: Повторять ли неудачные задания
            max_retries: Максимальное количество повторных попыток

        Returns:
            Результаты выполнения заданий
        """
        # Проверяем, авторизованы ли мы
        if not self.auth_client.user_id or not self.quest_client.user_id:
            logger.info(f"{self.user} не авторизован, выполняю авторизацию")
            auth_result = await self.login()

            if not auth_result:
                # Если получили ошибку о превышении лимита запросов
                if isinstance(auth_result, str) and auth_result == "RATE_LIMIT":
                    logger.warning(
                        f"{self.user} аккаунт поставлен в ожидание из-за ограничения запросов"
                    )
                    return {"status": "RATE_LIMITED"}

                logger.error(
                    f"{self.user} не удалось авторизоваться, выполнение заданий невозможно"
                )
                return {}

        # Выполняем все задания
        return await self.quest_client.complete_all_quests(
            retry_failed=retry_failed, max_retries=max_retries
        )

    async def complete_specific_quests(self, quest_names: List[str]) -> Dict[str, bool]:
        """
        Выполняет только указанные задания с обработкой ошибок

        Args:
            quest_names: Список названий заданий

        Returns:
            Результаты выполнения заданий
        """
        # Проверяем, авторизованы ли мы
        if not self.auth_client.user_id or not self.quest_client.user_id:
            logger.info(f"{self.user} не авторизован, выполняю авторизацию")
            auth_result = await self.login()

            if not auth_result:
                # Если получили ошибку о превышении лимита запросов
                if isinstance(auth_result, str) and auth_result == "RATE_LIMIT":
                    logger.warning(
                        f"{self.user} аккаунт поставлен в ожидание из-за ограничения запросов"
                    )
                    return {"status": "RATE_LIMITED"}

                logger.error(
                    f"{self.user} не удалось авторизоваться, выполнение заданий невозможно"
                )
                return {}

        # Выполняем указанные задания
        return await self.quest_client.complete_specific_quests(quest_names)

    async def get_stats(self) -> Dict[str, Any]:
        """
        Получает статистику выполнения заданий и баллов

        Returns:
            Статистика заданий
        """
        # Проверяем, авторизованы ли мы
        if not self.auth_client.user_id or not self.quest_client.user_id:
            logger.info(f"{self.user} не авторизован, выполняю авторизацию")
            if not await self.login():
                logger.error(
                    f"{self.user} не удалось авторизоваться, получение статистики невозможно"
                )
                return {"error": "Не удалось авторизоваться"}

        # Получаем статистику
        return await self.quest_client.get_stats()
