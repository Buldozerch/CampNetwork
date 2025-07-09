from .models import User
import random
import json
from datetime import datetime
from sqlalchemy import select, update, text
from libs.eth_async.utils.utils import parse_proxy


class DB:
    def __init__(self, session):
        self.session = session

    async def add_wallet(
        self,
        private_key: str,
        public_key: str,
        user_agent: str,
        proxy: str | None = None,
        twitter_token: str | None = None,
    ):
        """Добавляет кошелек в базу данных"""
        wallet = User(
            private_key=private_key,
            public_key=public_key,
            proxy=proxy,
            user_agent=user_agent,
            twitter_token=twitter_token,
            proxy_status="OK",
            twitter_status="OK",
        )
        try:
            self.session.add(wallet)
            await self.session.flush()  # Проверяем наличие ошибок при добавлении
        except Exception as e:
            return False
        return True

    async def update_proxy(self, user_id: int, available_proxies: list):
        """Обновляет прокси для пользователя"""
        existing_proxies = await self.session.execute(select(User.proxy))
        existing_proxies = {
            proxy[0] for proxy in existing_proxies.all()
        }  # Преобразуем в множество

        # Фильтруем список, оставляя только уникальные прокси
        unique_proxies = list(set(available_proxies) - existing_proxies)
        if not unique_proxies:
            raise ValueError("Нет доступных уникальных прокси!")

        # Выбираем случайный уникальный прокси
        new_proxy = random.choice(unique_proxies)
        new_proxy = parse_proxy(new_proxy)

        # Обновляем прокси для пользователя
        user = await self.session.get(User, user_id)
        if user:
            user.proxy = new_proxy
            user.proxy_status = "OK"  # Сбрасываем статус при обновлении
            await self.session.commit()
            return new_proxy
        else:
            raise ValueError(f"Пользователь с id {user_id} не найден")

    async def update_twitter_token(self, user_id: int, available_tokens: list):
        """Обновляет токен Twitter для пользователя"""
        existing_tokens = await self.session.execute(select(User.twitter_token))
        existing_tokens = {
            token[0] for token in existing_tokens.all() if token[0]
        }  # Преобразуем в множество

        # Фильтруем список, оставляя только уникальные токены
        unique_tokens = list(set(available_tokens) - existing_tokens)
        if not unique_tokens:
            raise ValueError("Нет доступных уникальных токенов Twitter!")

        # Выбираем случайный уникальный токен
        new_token = random.choice(unique_tokens)

        # Обновляем токен для пользователя
        user = await self.session.get(User, user_id)
        if user:
            user.twitter_token = new_token
            user.twitter_status = "OK"  # Сбрасываем статус при обновлении
            await self.session.commit()
            return new_token
        else:
            raise ValueError(f"Пользователь с id {user_id} не найден")

    async def get_all_wallets(self) -> list:
        """Получает все кошельки из базы данных"""
        result = await self.session.execute(
            select(User)
        )  # выполняем запрос ко всем записям в таблице
        wallets = result.scalars().all()  # возвращаем все строки из таблицы как список
        return wallets

    async def mark_quest_completed(self, user_id: int, quest_id: str) -> bool:
        """
        Отмечает задание как выполненное для указанного пользователя

        Args:
            user_id: ID пользователя
            quest_id: ID выполненного задания

        Returns:
            Статус успеха
        """
        try:
            # Получаем пользователя
            user = await self.session.get(User, user_id)
            if not user:
                return False

            # Получаем текущие выполненные квесты
            completed_quests = (
                user.completed_quests.split(",") if user.completed_quests else []
            )

            # Добавляем задание, если его там нет
            if quest_id not in completed_quests:
                completed_quests.append(quest_id)

            # Обновляем поле в БД
            user.completed_quests = ",".join(completed_quests)
            await self.session.commit()

            return True

        except Exception as e:
            return False

    async def is_quest_completed(self, user_id: int, quest_id: str) -> bool:
        """
        Проверяет, выполнено ли задание указанным пользователем

        Args:
            user_id: ID пользователя
            quest_id: ID задания

        Returns:
            Статус выполнения
        """
        try:
            # Получаем пользователя
            user = await self.session.get(User, user_id)
            if not user or not user.completed_quests:
                return False

            # Проверяем, есть ли задание в списке выполненных
            completed_quests = user.completed_quests.split(",")
            return quest_id in completed_quests

        except Exception as e:
            return False

    async def get_completed_quests(self, user_id: int) -> list:
        """
        Получает список выполненных заданий для указанного пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Список выполненных заданий (ID)
        """
        try:
            # Получаем пользователя
            user = await self.session.get(User, user_id)
            if not user or not user.completed_quests:
                return []

            # Возвращаем список выполненных заданий
            return user.completed_quests.split(",")

        except Exception as e:
            return []

    # --- Добавляем новые функции для управления ресурсами ---

    async def update_last_faucet_claim(self, user_id: int) -> bool:
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False
            user.faucet_last_claim = datetime.utcnow()
            return True
        except Exception as e:
            return False

    async def mark_account_as_blocked(self, user_id: int) -> bool:
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False
            user.account_blocked = True
            return True
        except Exception as e:
            return False

    async def mark_proxy_as_bad(self, user_id: int) -> bool:
        """
        Отмечает прокси пользователя как плохое

        Args:
            user_id: ID пользователя

        Returns:
            Статус успеха
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False

            user.proxy_status = "BAD"
            await self.session.commit()
            return True
        except Exception as e:
            return False

    async def mark_twitter_as_bad(self, user_id: int) -> bool:
        """
        Отмечает токен Twitter пользователя как плохой

        Args:
            user_id: ID пользователя

        Returns:
            Статус успеха
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False

            user.twitter_status = "BAD"
            await self.session.commit()
            return True
        except Exception as e:
            return False

    async def get_wallets_with_bad_proxy(self) -> list:
        """
        Получает список кошельков с плохими прокси

        Returns:
            Список кошельков
        """
        query = select(User).where(User.proxy_status == "BAD")
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_wallets_with_bad_twitter(self) -> list:
        """
        Получает список кошельков с плохими токенами Twitter

        Returns:
            Список кошельков
        """
        query = select(User).where(User.twitter_status == "BAD")
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_bad_resources_count(self) -> tuple:
        """
        Получает количество плохих ресурсов

        Returns:
            (bad_proxies, bad_twitter): Количество плохих ресурсов
        """
        bad_proxies_query = select(User).where(User.proxy_status == "BAD")
        bad_proxies_result = await self.session.execute(bad_proxies_query)
        bad_proxies = len(bad_proxies_result.scalars().all())

        bad_twitter_query = select(User).where(User.twitter_status == "BAD")
        bad_twitter_result = await self.session.execute(bad_twitter_query)
        bad_twitter = len(bad_twitter_result.scalars().all())

        return bad_proxies, bad_twitter

    async def replace_bad_proxy(self, user_id: int, new_proxy: str) -> bool:
        """
        Заменяет плохое прокси пользователя

        Args:
            user_id: ID пользователя
            new_proxy: Новое прокси

        Returns:
            Статус успеха
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False

            user.proxy = parse_proxy(new_proxy)
            user.proxy_status = "OK"
            await self.session.commit()
            return True
        except Exception as e:
            return False

    async def replace_bad_twitter(self, user_id: int, new_token: str) -> bool:
        """
        Заменяет плохой токен Twitter пользователя

        Args:
            user_id: ID пользователя
            new_token: Новый токен Twitter

        Returns:
            Статус успеха
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False

            user.twitter_token = new_token
            user.twitter_status = "OK"
            await self.session.commit()
            return True
        except Exception as e:
            return False

    async def update_ref_code(self, user_id: int, ref_code: str | None) -> bool:
        """
        Обновляет реферальный код пользователя

        Args:
            user_id: ID пользователя
            ref_code: Реферальный код

        Returns:
            Статус успеха
        """
        try:
            user = await self.session.get(User, user_id)
            if not user:
                return False

            if not ref_code:
                return False
            user.ref_code = ref_code
            await self.session.commit()
            return True
        except Exception as e:
            return False

    async def get_available_ref_codes(self) -> list:
        """
        Получает список доступных реферальных кодов из БД

        Returns:
            Список реферальных кодов
        """
        query = select(User.ref_code).where(User.ref_code != None)
        result = await self.session.execute(query)
        codes = [code[0] for code in result.all() if code[0]]
        return codes
