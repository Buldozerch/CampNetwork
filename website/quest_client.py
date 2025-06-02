import asyncio
import random
import json
from typing import Dict, List, Optional, Any
from loguru import logger
from website.http_client import BaseHttpClient
from utils.db_api_async.db_api import Session
from utils.db_api_async.db_activity import DB


class QuestClient(BaseHttpClient):
    """Клиент для взаимодействия с заданиями CampNetwork"""
    
    # ID заданий, собранные из curl-запросов
    QUEST_IDS = {
        "CampNetwork": "2585eb2f-7cac-45d1-88db-13608762bf17",
        "CampStory": "541ff274-95c5-409a-9ea2-c80ec2719d7e",
        "Bleetz": "10668db1-081d-40e2-9f42-06fafc67e4aa",
        "Cristal": "d4fdee29-c60f-40f2-8795-1da0e9e5414e",
        "Belgrano": "e6eda663-977e-4d71-a03c-a1020db88064",
        "SummitX": "211c9b79-ff65-42f8-a59a-ad0539129aa9",
        "Clusters": "3ea83621-0087-4fc1-9967-c21265e2c369",
        "PictoBot": "2ba6c29a-69a1-4ff8-ac61-f4b19431f8d2",
        "PanenkaTG": "be50eaa0-945a-4664-8d07-a2f02167cf38",
        "PictoCommunity": "2233dcaa-a2be-49fb-b322-28bf9d387475",
        "TokenTails": "06b0d411-c1df-4cc5-a72c-e47dc911a0b3",
        "AwanaTG": "9b87193e-c568-4a72-915d-1bdba060b00e",
        "Arcoin": "aa08b2a5-eaab-469c-9e6f-e3a380c23faa",
        "Pixudi": "9f8edb41-4867-48e0-8d7a-8437c2c6e1b1",
        "JukieBlox": "46a1b202-ab7b-4c29-bf13-417c6a8267af",
        "StoryChain": "4345ec66-0746-4a77-85d0-a79db42612b1",
        "ScorePlay": "e7c0f882-82b7-499e-8a05-40528e0047ee",
        "WideWorlds": "d0928019-b49f-4ffd-8450-d7f5d3821f59",
        "RewardedTv": "d7a3a18b-38fd-45d5-937a-f974dff403bd",
        "Kraft": "f4de4fa8-ad5c-45c9-a804-0483309de9f9",
        "Hitmakr": "afac07d2-6c0e-42ae-9dd8-1fff68ca6a49",
        "SummitXDis": "3dfca204-edf2-461a-8fda-4067b09241a7",
        "SummitXTG": "861e2917-3725-48ba-b8b9-4466cd81fe72"
    }
    
    # URL для запросов
    BASE_URL = "https://loyalty.campnetwork.xyz"
    COMPLETE_URL_TEMPLATE = f"{BASE_URL}/api/loyalty/rules/{{quest_id}}/complete"
    STATUS_URL = f"{BASE_URL}/api/loyalty/rules/status"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.completed_quests = []  # Список выполненных заданий в рамках текущей сессии
        self.quest_status = {}  # Статус всех заданий
        self.user_id = kwargs.get('user_id')  # ID пользователя
    
    def set_user_id(self, user_id: str) -> None:
        """
        Устанавливает ID пользователя
        
        Args:
            user_id: ID пользователя
        """
        self.user_id = user_id
    
    async def get_status_params(self) -> Dict[str, str]:
        """
        Получает параметры для запроса статуса заданий
        
        Returns:
            Параметры для запроса статуса
        """
        if not self.user_id:
            logger.error(f"{self.user} попытка получить параметры статуса без ID пользователя")
            return {}
            
        return {
            "userId": self.user_id,
            "websiteId": "32afc5c9-f0fb-4938-9572-775dee0b4a2b",
            "organizationId": "26a1764f-5637-425e-89fa-2f3fb86e758c"
        }
    
    async def check_quests_status(self) -> Dict:
        """
        Проверяет статус всех заданий
        
        Returns:
            Статус заданий
        """
        params = await self.get_status_params()
        if not params:
            return {}
            
        success, response = await self.request(
            url=self.STATUS_URL,
            method="GET",
            params=params
        )
        
        if success and isinstance(response, dict):
            self.quest_status = response
            logger.info(f"{self.user} получен статус заданий (всего {len(response.get('rules', []))})")
            return response
        else:
            logger.error(f"{self.user} не удалось получить статус заданий: {response}")
            return {}


    async def get_db_completed_quests(self) -> List[str]:
        """
        Получает список выполненных заданий из базы данных
        
        Returns:
            Список ID выполненных заданий
        """
        try:
            async with Session() as session:
                db = DB(session=session)
                completed_quests = await db.get_completed_quests(self.user.id)
                
                # Обновляем список выполненных заданий в текущей сессии (названия квестов)
                self.completed_quests = [
                    quest_name for quest_name, quest_id in self.QUEST_IDS.items() 
                    if quest_id in completed_quests
                ]
                
                return completed_quests
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при получении выполненных заданий из БД: {e}")
            return []

    async def get_incomplete_quests(self) -> List[str]:
        """
        Получает список незавершенных заданий, используя данные из БД
        
        Returns:
            Список незавершенных заданий (названий)
        """
        # Получаем выполненные задания из БД
        completed_quests_ids = await self.get_db_completed_quests()
        
        # Формируем список незавершенных заданий
        incomplete_quests = []
        
        for quest_name, quest_id in self.QUEST_IDS.items():
            # Проверяем, нет ли ID задания в списке выполненных
            if quest_id not in completed_quests_ids:
                incomplete_quests.append(quest_name)
        
        logger.info(f"{self.user} незавершенные задания ({len(incomplete_quests)}): {', '.join(incomplete_quests) if incomplete_quests else 'нет'}")
        return incomplete_quests

    async def mark_quest_completed(self, quest_name: str) -> bool:
        """
        Отмечает задание как выполненное в БД
        
        Args:
            quest_name: Название задания
            
        Returns:
            Статус успеха
        """
        try:
            async with Session() as session:
                db = DB(session=session)
                result = await db.mark_quest_completed(self.user.id, quest_name)
                
                if result:
                    # Добавляем в локальный список выполненных заданий
                    if quest_name not in self.completed_quests:
                        self.completed_quests.append(quest_name)
                        
                    return True
                else:
                    return False
                    
        except Exception as e:
            logger.error(f"{self.user} ошибка при отметке задания {quest_name} как выполненного: {e}")
            return False
    
    async def is_quest_completed(self, quest_name: str) -> bool:
        """
        Проверяет, выполнено ли задание
        
        Args:
            quest_name: Название задания
            
        Returns:
            Статус выполнения
        """
        # Сначала проверяем в локальном списке выполненных заданий
        if quest_name in self.completed_quests:
            return True
            
        # Затем проверяем в БД
        try:
            async with Session() as session:
                db = DB(session=session)
                return await db.is_quest_completed(self.user.id, quest_name)
                
        except Exception as e:
            logger.error(f"{self.user} ошибка при проверке статуса задания {quest_name}: {e}")
            return False

    async def complete_quest(self, quest_name: str) -> bool:
        """
        Выполняет задание по его имени и сохраняет результат в БД
        
        Args:
            quest_name: Название задания
            
        Returns:
            Статус успеха
        """
        # Получаем ID задания
        quest_id = self.QUEST_IDS.get(quest_name)
        if not quest_id:
            logger.error(f"Задание {quest_name} не найдено в списке")
            return False
        
        # Проверяем, не выполнено ли уже задание
        try:
            async with Session() as session:
                db = DB(session=session)
                if await db.is_quest_completed(self.user.id, quest_id):
                    logger.info(f"{self.user} задание {quest_name} (ID: {quest_id}) уже выполнено ранее (из БД)")
                    return True
        except Exception as e:
            logger.error(f"{self.user} ошибка при проверке статуса задания в БД: {e}")
        
        try:
            url = self.COMPLETE_URL_TEMPLATE.format(quest_id=quest_id)
            
            # Добавляем случайную задержку для имитации человеческого поведения
            await asyncio.sleep(random.uniform(1.5, 4.0))
            
            logger.info(f"{self.user} выполняет задание {quest_name} (ID: {quest_id})")
            
            headers = await self.get_headers({
                'Content-Type': 'application/json',
                'Origin': 'https://loyalty.campnetwork.xyz',
                'Priority': 'u=0',
            })
            
            success, response = await self.request(
                url=url,
                method="POST",
                json_data={},  # Пустой JSON как в curl-запросах
                headers=headers
            )
            
            if success:
                logger.success(f"{self.user} успешно выполнил задание {quest_name} (ID: {quest_id})")
                # Отмечаем задание как выполненное в БД
                try:
                    async with Session() as session:
                        db = DB(session=session)
                        mark_result = await db.mark_quest_completed(self.user.id, quest_id)
                        
                        if mark_result:
                            pass
                            # logger.debug(f"{self.user} задание {quest_name} (ID: {quest_id}) успешно отмечено в БД")
                        else:
                            logger.warning(f"{self.user} не удалось отметить задание {quest_name} (ID: {quest_id}) в БД")
                except Exception as e:
                    logger.error(f"{self.user} ошибка при сохранении статуса задания в БД: {e}")
                    
                return True
            else:
                # Проверяем, может быть задание уже выполнено
                if isinstance(response, dict) and response.get("message") == "You have already been rewarded" and response.get("rewarded") is True:
                    logger.info(f"{self.user} задание {quest_name} (ID: {quest_id}) уже выполнено ранее (ответ сервера)")
                    # Отмечаем задание как выполненное в БД
                    try:
                        async with Session() as session:
                            db = DB(session=session)
                            await db.mark_quest_completed(self.user.id, quest_id)
                    except Exception as e:
                        logger.error(f"{self.user} ошибка при сохранении статуса задания в БД: {e}")
                    return True  # Считаем это успешным выполнением
                else:
                    logger.error(f"{self.user} ошибка при выполнении задания {quest_name} (ID: {quest_id}): {response}")
                    return False
                
        except Exception as e:
            logger.error(f"{self.user} исключение при выполнении задания {quest_name} (ID: {quest_id}): {e}")
            return False   

    async def complete_all_quests(self, retry_failed: bool = True, max_retries: int = 3) -> Dict[str, bool]:
        """
        Выполняет все незавершенные задания в случайном порядке
        
        Args:
            retry_failed: Повторять ли неудачные задания
            max_retries: Максимальное количество повторных попыток
            
        Returns:
            Результаты выполнения заданий
        """
        results = {}
        
        # Получаем список незавершенных заданий
        incomplete_quests = await self.get_incomplete_quests()
        
        if not incomplete_quests:
            logger.success(f"{self.user} все задания уже выполнены")
            return results
        
        # Перемешиваем список заданий для случайного порядка выполнения
        random.shuffle(incomplete_quests)
        
        # Словарь для отслеживания попыток
        retry_counts = {quest: 0 for quest in incomplete_quests}
        
        # Выполняем задания
        for quest_name in incomplete_quests:
            success = await self.complete_quest(quest_name)
            results[quest_name] = success
            
            # Увеличенная задержка между заданиями (20-30 секунд)
            await asyncio.sleep(random.uniform(20.0, 30.0))
        
        # Проверяем результаты и повторяем неудачные задания если нужно
        if retry_failed:
            # Получаем обновленный список незавершенных заданий
            remaining = await self.get_incomplete_quests()
            
            # Повторяем неудачные задания
            for quest_name in remaining:
                # Учитываем только задания из первоначального списка
                if quest_name in retry_counts:
                    retry_counts[quest_name] += 1
                    
                    if retry_counts[quest_name] <= max_retries:
                        logger.warning(f"{self.user} повторная попытка {retry_counts[quest_name]}/{max_retries} для задания {quest_name}")
                        
                        # Задержка перед повторной попыткой (30-40 секунд)
                        await asyncio.sleep(random.uniform(30.0, 40.0))
                        
                        success = await self.complete_quest(quest_name)
                        results[quest_name] = success
        
        # Получаем итоговую статистику
        completed = sum(1 for result in results.values() if result)
        logger.success(f"{self.user} выполнено {completed} из {len(results)} заданий")
        
        return results
    
    async def complete_specific_quests(self, quest_names: List[str]) -> Dict[str, bool]:
        """
        Выполняет только указанные задания в случайном порядке
        
        Args:
            quest_names: Список названий заданий
            
        Returns:
            Результаты выполнения заданий
        """
        results = {}
        
        # Проверяем, что все указанные задания существуют
        invalid_quests = [name for name in quest_names if name not in self.QUEST_IDS]
        if invalid_quests:
            logger.warning(f"{self.user} следующие задания не найдены: {', '.join(invalid_quests)}")
        
        # Фильтруем только существующие задания
        valid_quests = [name for name in quest_names if name in self.QUEST_IDS]
        
        if not valid_quests:
            logger.error(f"{self.user} нет действительных заданий для выполнения")
            return results
        
        # Фильтруем задания, которые еще не выполнены
        not_completed_quests = []
        for quest_name in valid_quests:
            if not await self.is_quest_completed(quest_name):
                not_completed_quests.append(quest_name)
        
        if not not_completed_quests:
            logger.info(f"{self.user} все указанные задания уже выполнены")
            return results
        
        # Перемешиваем список заданий для случайного порядка выполнения
        random.shuffle(not_completed_quests)
        
        # Выполняем задания
        for quest_name in not_completed_quests:
            success = await self.complete_quest(quest_name)
            results[quest_name] = success
            
            # Увеличенная задержка между заданиями (20-30 секунд)
            await asyncio.sleep(random.uniform(20.0, 30.0))
        
        return results
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Получает статистику выполнения заданий и баллов
        
        Returns:
            Статистика заданий
        """
        # Получаем выполненные задания из БД
        completed_quests = await self.get_db_completed_quests()
        completed_count = sum(1 for status in completed_quests.values() if status)
        
        # Пробуем получить статус с сервера для общей статистики
        try:
            status = await self.check_quests_status()
            total_points = status.get('totalPoints', 0) if status else 0
        except:
            total_points = 0
        
        return {
            "completed_count": completed_count,
            "total_count": len(self.QUEST_IDS),
            "total_points": total_points
        }
