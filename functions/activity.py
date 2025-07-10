import os
from loguru import logger
import random
import asyncio
from datetime import datetime
from website import auth_client
from website.camp_client import CampNetworkClient
from typing import List, Tuple
from website.twitter import TwitterClient
from website.quest_client import QuestClient
from website.resource_manager import ResourceManager
from tasks.faucet import Faucet, FaucetError, CaptchaUnsolvableError, RateLimitError
from tasks.camp_onchain import CampOnchain
from libs.eth_async.client import Client
from libs.eth_async import create_client
from libs.eth_async.utils.utils import parse_proxy
from libs.eth_async.data.models import Networks
from utils.db_api_async.db_api import Session
from utils.db_api_async.models import User
from utils.db_api_async.db_activity import DB
from data import config
from data.config import ACTUAL_FOLLOWS_TWITTER, ACTUAL_UA, SOLVECAPTCHA_API_KEY
from data.models import Settings

settings = Settings()

# Загружаем данные из файлов
private_file = config.PRIVATE_FILE
if os.path.exists(private_file):
    with open(private_file, "r") as private_file:
        private = [line.strip() for line in private_file if line.strip()]
else:
    private = []

proxy_file = config.PROXY_FILE
if os.path.exists(proxy_file):
    with open(proxy_file, "r") as proxy_file:
        proxys = [line.strip() for line in proxy_file if line.strip()]
else:
    proxys = []

twitter_file = config.TWITTER_FILE
if os.path.exists(twitter_file):
    with open(twitter_file, "r") as twitter_file:
        twitter = [line.strip() for line in twitter_file if line.strip()]
else:
    twitter = []


async def add_wallets_db():
    """Импортирует кошельки в базу данных"""
    if not private:
        logger.error("Нет приватных ключей в файле private.txt")
        return

    logger.info(f"Импортирую {len(private)} кошельков в базу данных")
    for i in range(len(private)):
        user_agent = ACTUAL_UA
        private_key = private[i]
        proxy = proxys[i] if i < len(proxys) else None
        proxy = parse_proxy(proxy) if proxy else None
        twitter_token = twitter[i] if i < len(twitter) else None

        try:
            client = Client(private_key=private_key, network=Networks.Ethereum)
            public_key = client.account.address

            async with Session() as session:
                db = DB(session=session)
                success = await db.add_wallet(
                    private_key=private_key,
                    public_key=public_key,
                    proxy=proxy,
                    user_agent=user_agent,
                    twitter_token=twitter_token,
                )

                if success:
                    logger.success(f"Кошелек {public_key} добавлен в базу данных")
                else:
                    logger.warning(f"Кошелек {public_key} уже существует в базе данных")
        except Exception as e:
            logger.error(f"Ошибка при добавлении кошелька: {str(e)}")

    logger.success("Импорт кошельков завершен")
    return


async def process_wallet(wallet: User):
    """
    Обрабатывает все задания для одного кошелька с обработкой ошибок ресурсов

    Args:
        wallet: Объект кошелька

    Returns:
        Статус успеха
    """
    if wallet.account_blocked:
        logger.warning(f"{wallet} account is blocked")
        return False

    resource_manager = ResourceManager()
    settings = Settings()
    auto_replace, max_failures = settings.get_resource_settings()

    # Счетчики ошибок
    proxy_errors = 0

    # Для отслеживания необходимости повторной попытки
    retry_with_new_proxy = True
    max_retries = 3
    retry_count = 0

    twitter_enabled = settings.twitter_enabled and wallet.twitter_token is not None

    # Получаем список незавершенных заданий
    async with Session() as session:
        db = DB(session=session)
        completed_quests_ids = (
            wallet.completed_quests.split(",") if wallet.completed_quests else []
        )
        all_quests_ids = list(QuestClient.QUEST_IDS.values())

        # Фильтруем только те задания, которые еще не выполнены
        incomplete_quests_ids = [
            quest_id
            for quest_id in all_quests_ids
            if quest_id not in completed_quests_ids
        ]

        # Преобразуем ID заданий обратно в имена
        incomplete_quests = []
        for quest_id in incomplete_quests_ids:
            for quest_name, qid in QuestClient.QUEST_IDS.items():
                if qid == quest_id:
                    incomplete_quests.append(quest_name)
                    break

    # Получаем список всех Twitter заданий (подписок)
    twitter_follow_tasks = []
    if twitter_enabled:
        for account_name in settings.twitter_follow_accounts:
            quest_id = TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {}).get(
                account_name
            )
            if quest_id and quest_id not in completed_quests_ids:
                twitter_follow_tasks.append(account_name)

    # Считаем общее количество всех заданий
    if settings.twitter_enabled:
        total_tasks = len(incomplete_quests) + len(twitter_follow_tasks)
    else:
        total_tasks = len(incomplete_quests)

    if total_tasks == 0:
        logger.success(f"{wallet} все задания уже выполнены")
        return True

    startup_min, startup_max = settings.get_wallet_startup_delay()
    delay = random.uniform(startup_min, startup_max)
    logger.info(f"Запуск кошелька {wallet} через {int(delay)} сек.")
    await asyncio.sleep(delay)
    while retry_with_new_proxy and retry_count < max_retries:
        try:
            # Если это повторная попытка с новым прокси, обновляем данные о кошельке
            if retry_count > 0:
                async with Session() as session:
                    wallet = await session.get(User, wallet.id)
                    if not wallet:
                        logger.error(
                            f"Не удалось получить обновленные данные кошелька с ID {wallet.id}"
                        )
                        return False

            logger.info(
                f"Начинаю работу с {wallet} (попытка {retry_count + 1}/{max_retries})"
            )

            # Создаем клиент CampNetwork
            camp_client = CampNetworkClient(user=wallet)

            # Авторизуемся на сайте
            auth_success, response = await camp_client.login()
            if not auth_success:
                logger.error(f"{wallet} не удалось авторизоваться на CampNetwork")

                # Проверяем, связана ли проблема с прокси
                if (
                    "proxy" in str(response).lower()
                    or "connection" in str(response).lower()
                ):
                    proxy_errors += 1
                    logger.warning(
                        f"{wallet} возможно проблема с прокси (ошибка {proxy_errors}/{max_failures})"
                    )

                    # Если достигнут порог ошибок, отмечаем прокси как плохое
                    if proxy_errors >= max_failures:
                        await resource_manager.mark_proxy_as_bad(wallet.id)

                        # Если включена автозамена, пробуем заменить прокси
                        if auto_replace:
                            success, message = await resource_manager.replace_proxy(
                                wallet.id
                            )
                            if success:
                                logger.info(
                                    f"{wallet} прокси заменено: {message}, пробуем снова..."
                                )
                                retry_count += 1
                                continue  # Пробуем снова с новым прокси
                            else:
                                logger.error(
                                    f"{wallet} не удалось заменить прокси: {message}"
                                )
                                retry_with_new_proxy = False  # Прекращаем попытки
                                return False
                elif "WALLET_ADDRESS_BLOCKED".lower() in str(response).lower():
                    logger.error(f"{wallet} account blocked")
                    await resource_manager.mark_wallet_as_blocked(wallet.id)
                    return False

                # Если проблема не с прокси или нет автозамены, выходим
                retry_with_new_proxy = False
                return False

            # Если авторизация успешна, прекращаем цикл повторных попыток
            retry_with_new_proxy = False

            # Проверяем, включен ли Twitter
            twitter_enabled = (
                settings.twitter_enabled and wallet.twitter_token is not None
            )

            # Получаем список незавершенных заданий
            async with Session() as session:
                db = DB(session=session)
                completed_quests_ids = (
                    wallet.completed_quests.split(",")
                    if wallet.completed_quests
                    else []
                )
                all_quests_ids = list(QuestClient.QUEST_IDS.values())

                # Фильтруем только те задания, которые еще не выполнены
                incomplete_quests_ids = [
                    quest_id
                    for quest_id in all_quests_ids
                    if quest_id not in completed_quests_ids
                ]

                # Преобразуем ID заданий обратно в имена
                incomplete_quests = []
                for quest_id in incomplete_quests_ids:
                    for quest_name, qid in QuestClient.QUEST_IDS.items():
                        if qid == quest_id:
                            incomplete_quests.append(quest_name)
                            break

            # Получаем список всех Twitter заданий (подписок)
            twitter_follow_tasks = []
            if twitter_enabled:
                for account_name in settings.twitter_follow_accounts:
                    quest_id = TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {}).get(
                        account_name
                    )
                    if quest_id and quest_id not in completed_quests_ids:
                        twitter_follow_tasks.append(account_name)

            # Считаем общее количество всех заданий
            total_tasks = len(incomplete_quests) + len(twitter_follow_tasks)

            if total_tasks == 0:
                logger.success(f"{wallet} все задания уже выполнены")
                return True

            logger.info(
                f"{wallet} найдено {len(incomplete_quests)} обычных заданий и {len(twitter_follow_tasks)} Twitter заданий для выполнения"
            )

            # Получаем настройки задержек для обычных заданий
            regular_min_delay, regular_max_delay = settings.get_quest_delay()

            # Выполняем обычные задания
            regular_completed = 0
            if incomplete_quests:
                logger.info(
                    f"{wallet} выполняю регулярные задания ({len(incomplete_quests)})"
                )

                # Перемешиваем список заданий для рандомизации
                random.shuffle(incomplete_quests)

                for quest_name in incomplete_quests:
                    try:
                        logger.info(f"{wallet} выполняю задание {quest_name}")
                        result = await camp_client.quest_client.complete_quest(
                            quest_name
                        )

                        if result:
                            logger.success(
                                f"{wallet} успешно выполнено задание {quest_name}"
                            )
                            regular_completed += 1
                        else:
                            logger.warning(
                                f"{wallet} не удалось выполнить задание {quest_name}"
                            )

                        # Задержка между заданиями
                        delay = random.uniform(regular_min_delay, regular_max_delay)
                        logger.info(
                            f"{wallet} задержка {int(delay)} сек. перед следующим заданием"
                        )
                        await asyncio.sleep(delay)

                    except Exception as e:
                        logger.error(
                            f"{wallet} ошибка при выполнении задания {quest_name}: {str(e)}"
                        )

                        # Проверяем, может быть проблема с прокси
                        if (
                            "proxy" in str(e).lower()
                            or "connection" in str(e).lower()
                            or "timeout" in str(e).lower()
                        ):
                            proxy_errors += 1
                            logger.warning(
                                f"{wallet} возможно проблема с прокси (ошибка {proxy_errors}/{max_failures})"
                            )

                            # Если достигнут порог ошибок, отмечаем прокси как плохое
                            if proxy_errors >= max_failures:
                                await resource_manager.mark_proxy_as_bad(wallet.id)

                        await asyncio.sleep(
                            regular_min_delay
                        )  # Минимальная задержка перед следующим заданием
                        continue

            # Выполняем Twitter задания, если Twitter включен и есть задания
            twitter_completed_count = 0
            if twitter_enabled and twitter_follow_tasks:
                twitter_result, twitter_completed_count = await process_twitter_tasks(
                    wallet=wallet,
                    camp_client=camp_client,
                    resource_manager=resource_manager,
                    settings=settings,
                    follow_accounts=twitter_follow_tasks,
                )

                if twitter_result:
                    logger.success(
                        f"{wallet} успешно выполнено {twitter_completed_count} из {len(twitter_follow_tasks)} Twitter заданий"
                    )
                else:
                    logger.warning(
                        f"{wallet} Twitter задания выполнены частично: {twitter_completed_count} из {len(twitter_follow_tasks)}"
                    )

            # Получаем список выполненных квестов для проверки
            async with Session() as session:
                db = DB(session=session)
                final_completed_quests = await db.get_completed_quests(wallet.id)

            # Подсчитываем количество выполненных заданий
            completed_count = (
                len(final_completed_quests) if final_completed_quests else 0
            )

            # Выводим итоговую статистику
            total_all_quests = len(QuestClient.QUEST_IDS) + len(
                TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {})
            )

            logger.success(
                f"{wallet} выполнение заданий завершено. Статус: {completed_count}/{total_all_quests} заданий"
            )
            logger.info(
                f"{wallet} успешно выполнено обычных заданий: {regular_completed} из {len(incomplete_quests)}"
            )
            logger.info(
                f"{wallet} успешно выполнено Twitter заданий: {twitter_completed_count} из {len(twitter_follow_tasks)}"
            )

            # Считаем задание успешным, если выполнено хотя бы одно задание
            return regular_completed > 0 or twitter_completed_count > 0

        except Exception as e:
            logger.error(f"{wallet} ошибка при обработке: {str(e)}")

            # Проверяем, может быть проблема с прокси
            if (
                "proxy" in str(e).lower()
                or "connection" in str(e).lower()
                or "timeout" in str(e).lower()
            ):
                proxy_errors += 1
                logger.warning(
                    f"{wallet} возможно проблема с прокси (ошибка {proxy_errors}/{max_failures})"
                )

                # Если достигнут порог ошибок, отмечаем прокси как плохое
                if proxy_errors >= max_failures:
                    await resource_manager.mark_proxy_as_bad(wallet.id)

                    # Если включена автозамена, пробуем заменить прокси
                    if auto_replace:
                        success, message = await resource_manager.replace_proxy(
                            wallet.id
                        )
                        if success:
                            logger.info(
                                f"{wallet} прокси заменено: {message}, пробуем снова..."
                            )
                            retry_count += 1
                            continue  # Пробуем снова с новым прокси
                        else:
                            logger.error(
                                f"{wallet} не удалось заменить прокси: {message}"
                            )
                else:
                    await asyncio.sleep(10)
                    retry_count += 1
                    continue

            # Если проблема не с прокси или не удалось заменить прокси
            return False

    # Если исчерпаны все попытки
    if retry_count >= max_retries:
        logger.error(f"{wallet} исчерпаны все {max_retries} попытки с заменой прокси")

    return False


async def process_twitter_tasks(
    wallet: User, camp_client, resource_manager, settings, follow_accounts: List[str]
) -> Tuple[bool, int]:
    """
    Отдельная функция для обработки Twitter заданий с повторными попытками и правильной заменой токенов

    Args:
        wallet: Объект кошелька
        camp_client: Клиент CampNetwork
        resource_manager: Менеджер ресурсов
        settings: Настройки
        follow_accounts: Список аккаунтов для подписки

    Returns:
        Tuple[success, completed_count]: Статус успеха и количество выполненных заданий
    """
    twitter_errors = 0
    max_failures = settings.resources_max_failures
    auto_replace = settings.resources_auto_replace
    max_twitter_retries = 4
    twitter_retry_count = 0
    completed_count = 0
    twitter_min_delay, twitter_max_delay = settings.get_twitter_quest_delay()

    # Проверка на ограничения Twitter
    daily_limit_reached = False
    random.shuffle(follow_accounts)

    # Для каждой попытки выполнения Twitter заданий
    while twitter_retry_count < max_twitter_retries:
        logger.info(
            f"{wallet} выполняю Twitter задания (попытка {twitter_retry_count + 1}/{max_twitter_retries})"
        )

        # Переменная для отслеживания инициализированного клиента
        twitter_client = None

        try:
            # Создаем Twitter клиент
            twitter_client = TwitterClient(
                user=wallet,
                auth_client=camp_client.auth_client,
                twitter_auth_token=wallet.twitter_token,
            )

            # ВАЖНО: Инициализируем клиент
            init_success = await twitter_client.initialize()
            if not init_success:
                logger.error(f"{wallet} не удалось инициализировать Twitter клиент")

                # Добавляем задержку после ошибки
                error_delay = random.uniform(2, 3)
                logger.info(f"{wallet} задержка {error_delay:.1f} сек. после ошибки")
                await asyncio.sleep(error_delay)

                # Если не удалось инициализировать, пробуем заменить токен
                if auto_replace and twitter_retry_count < max_failures:
                    logger.warning(
                        f"{wallet} не удалось инициализировать Twitter клиент, пробуем заменить токен"
                    )

                    # Отмечаем токен как плохой
                    await resource_manager.mark_twitter_as_bad(wallet.id)

                    success, message = await resource_manager.replace_twitter(wallet.id)
                    if success:
                        logger.info(f"{wallet} токен Twitter заменен в БД: {message}")

                        # Обновляем токен в кошельке из БД
                        async with Session() as session:
                            updated_wallet = await session.get(User, wallet.id)
                            if updated_wallet and updated_wallet.twitter_token:
                                # Используем функцию замены токена
                                replace_success = (
                                    await twitter_client.replace_twitter_token(
                                        updated_wallet.twitter_token
                                    )
                                )
                                if replace_success:
                                    logger.success(
                                        f"{wallet} успешно заменен токен Twitter на сайте"
                                    )
                                    wallet.twitter_token = updated_wallet.twitter_token
                                    # Прерываем текущий цикл попыток подключения
                                    twitter_retry_count += 1
                                    continue
                                else:
                                    logger.error(
                                        f"{wallet} не удалось заменить токен Twitter на сайте"
                                    )
                                    # Продолжаем со следующей основной итерацией
                                    twitter_retry_count += 1
                                    continue
                    else:
                        logger.error(
                            f"{wallet} не удалось заменить токен Twitter: {message}"
                        )
                        await resource_manager.mark_twitter_as_bad(wallet.id)
                        return False, completed_count
                else:
                    logger.error(f"{wallet} не удалось инициализировать Twitter клиент")
                    await resource_manager.mark_twitter_as_bad(wallet.id)
                    return False, completed_count

            # Проверяем подключение Twitter и переподключаем при необходимости
            connect_attempts = 0
            max_connect_attempts = 3  # Максимальное количество попыток подключения

            while connect_attempts < max_connect_attempts:
                twitter_connected = (
                    await twitter_client.check_twitter_connection_status()
                )

                if twitter_connected:
                    logger.success(f"{wallet} Twitter аккаунт подключен к CampNetwork")
                    break

                logger.info(
                    f"{wallet} Twitter не подключен, выполняю подключение (попытка {connect_attempts + 1}/{max_connect_attempts})"
                )

                # Подключаем Twitter аккаунт к CampNetwork
                connect_success = await twitter_client.connect_twitter_to_camp()

                if connect_success:
                    logger.success(f"{wallet} успешно подключил Twitter к CampNetwork")
                    break
                else:
                    connect_attempts += 1
                    logger.error(
                        f"{wallet} не удалось подключить Twitter к CampNetwork (попытка {connect_attempts}/{max_connect_attempts})"
                    )

                    # Добавляем задержку после ошибки
                    error_delay = random.uniform(
                        3, 5
                    )  # Увеличенная задержка для подключения
                    logger.info(
                        f"{wallet} задержка {error_delay:.1f} сек. перед следующей попыткой"
                    )
                    await asyncio.sleep(error_delay)

                    # Проверяем, может быть проблема с токеном Twitter
                    if connect_attempts >= max_connect_attempts:
                        last_error = getattr(twitter_client, "last_error", "")
                        if last_error and any(
                            x in str(last_error).lower()
                            for x in [
                                "unauthorized",
                                "auth",
                                "token",
                                "login",
                                "limit",
                                "unable to follow",
                            ]
                        ):
                            logger.warning(
                                f"{wallet} проблема с токеном Twitter: {last_error}"
                            )
                            await resource_manager.mark_twitter_as_bad(wallet.id)

                            # Если включена автозамена, пробуем заменить токен
                            if (
                                auto_replace
                                and twitter_retry_count < max_twitter_retries - 1
                            ):
                                (
                                    success,
                                    message,
                                ) = await resource_manager.replace_twitter(wallet.id)
                                if success:
                                    logger.info(
                                        f"{wallet} токен Twitter заменен в БД: {message}, выполняю замену на сайте..."
                                    )

                                    # Получаем новый токен из БД
                                    async with Session() as session:
                                        updated_wallet = await session.get(
                                            User, wallet.id
                                        )
                                        if (
                                            updated_wallet
                                            and updated_wallet.twitter_token
                                        ):
                                            # Используем функцию замены токена
                                            replace_success = await twitter_client.replace_twitter_token(
                                                updated_wallet.twitter_token
                                            )
                                            if replace_success:
                                                logger.success(
                                                    f"{wallet} успешно заменен токен Twitter на сайте"
                                                )
                                                wallet.twitter_token = (
                                                    updated_wallet.twitter_token
                                                )
                                                # Прерываем текущий цикл попыток подключения
                                                break
                                            else:
                                                logger.error(
                                                    f"{wallet} не удалось заменить токен Twitter на сайте"
                                                )
                                                # Продолжаем со следующей основной итерацией
                                                twitter_retry_count += 1
                                                break
                                else:
                                    logger.error(
                                        f"{wallet} не удалось заменить токен Twitter: {message}"
                                    )
                                    return False, completed_count

            # Проверяем, подключился ли Twitter после всех попыток
            if connect_attempts >= max_connect_attempts:
                if twitter_retry_count < max_twitter_retries - 1:
                    # Еще есть попытки основного цикла, продолжим со следующей итерацией
                    twitter_retry_count += 1
                    continue
                else:
                    logger.error(
                        f"{wallet} не удалось подключить Twitter к CampNetwork после всех попыток"
                    )
                    return False, completed_count

            # Если дневной лимит уже достигнут, пропускаем выполнение заданий
            if daily_limit_reached:
                logger.warning(
                    f"{wallet} достигнут дневной лимит Twitter, пропускаем оставшиеся задания"
                )
                # Возвращаем статус частичного успеха, если были выполнены задания
                return completed_count > 0, completed_count

            # Обрабатываем каждый аккаунт как отдельное задание
            for i, account_name in enumerate(follow_accounts):
                try:
                    # Получаем ID задания для этого аккаунта
                    quest_id = TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {}).get(
                        account_name
                    )
                    if not quest_id:
                        logger.warning(
                            f"{wallet} нет ID задания для подписки на {account_name}"
                        )
                        continue

                    # Проверяем, выполнено ли уже задание в БД
                    async with Session() as session:
                        db = DB(session=session)
                        if await db.is_quest_completed(wallet.id, quest_id):
                            logger.info(
                                f"{wallet} задание подписки на {account_name} уже выполнено"
                            )
                            completed_count += 1
                            continue

                    logger.info(f"{wallet} выполняю задание подписки на {account_name}")

                    # Используем метод follow_account с обработкой ограничений Twitter
                    (
                        follow_success,
                        error_message,
                        already_following,
                    ) = await twitter_client.follow_account(account_name)

                    # Обрабатываем случай, когда подписка не удалась и мы не были подписаны ранее
                    if not follow_success and not already_following:
                        if error_message:
                            if (
                                "лимит подписок" in error_message
                                or "дневной лимит" in error_message
                            ):
                                logger.warning(f"{wallet} {error_message}")
                                daily_limit_reached = True
                                # Прекращаем выполнение остальных заданий
                                break
                            else:
                                logger.error(
                                    f"{wallet} ошибка при подписке на {account_name}: {error_message}"
                                )
                                # Добавляем задержку после ошибки
                                error_delay = random.uniform(30, 60)
                                logger.info(
                                    f"{wallet} задержка {error_delay:.1f} сек. после ошибки"
                                )
                                await asyncio.sleep(error_delay)
                                continue

                    # Если подписка успешна или мы уже подписаны, пробуем выполнить задание
                    if follow_success or already_following:
                        # Если мы уже подписаны, отмечаем это в логе
                        if already_following:
                            logger.info(
                                f"{wallet} уже подписан на {account_name}, пробуем выполнить задание"
                            )

                        # Отправляем запрос на выполнение задания с повторными попытками
                        complete_url = f"{camp_client.auth_client.BASE_URL}/api/loyalty/rules/{quest_id}/complete"

                        headers = await camp_client.auth_client.get_headers(
                            {
                                "Accept": "application/json, text/plain, */*",
                                "Content-Type": "application/json",
                                "Origin": "https://loyalty.campnetwork.xyz",
                            }
                        )

                        # Делаем несколько попыток выполнения задания
                        complete_attempts = 0
                        max_complete_attempts = (
                            3  # Максимальное количество попыток выполнения задания
                        )

                        while complete_attempts < max_complete_attempts:
                            success, response = await camp_client.auth_client.request(
                                url=complete_url,
                                method="POST",
                                json_data={},
                                headers=headers,
                            )

                            if success:
                                logger.success(
                                    f"{wallet} успешно выполнено задание подписки на {account_name}"
                                )
                                completed_count += 1

                                # Отмечаем задание как выполненное в БД
                                async with Session() as session:
                                    db = DB(session=session)
                                    await db.mark_quest_completed(wallet.id, quest_id)

                                # Успех, выходим из цикла попыток
                                break

                            elif (
                                isinstance(response, dict)
                                and response.get("message")
                                == "You have already been rewarded"
                            ):
                                logger.info(
                                    f"{wallet} задание подписки на {account_name} уже отмечено как выполненное"
                                )
                                completed_count += 1

                                # Отмечаем задание как выполненное в БД
                                async with Session() as session:
                                    db = DB(session=session)
                                    await db.mark_quest_completed(wallet.id, quest_id)

                                # Успех, выходим из цикла попыток
                                break

                            else:
                                complete_attempts += 1
                                logger.warning(
                                    f"{wallet} не удалось выполнить задание подписки на {account_name} (попытка {complete_attempts}/{max_complete_attempts})"
                                )

                                if complete_attempts < max_complete_attempts:
                                    # Добавляем задержку перед следующей попыткой
                                    retry_delay = random.uniform(
                                        5, 10
                                    )  # Увеличенная задержка между попытками
                                    logger.info(
                                        f"{wallet} задержка {retry_delay:.1f} сек. перед повторной попыткой выполнения задания"
                                    )
                                    await asyncio.sleep(retry_delay)
                                else:
                                    logger.error(
                                        f"{wallet} не удалось выполнить задание подписки на {account_name} после {max_complete_attempts} попыток"
                                    )

                    # Добавляем задержку между заданиями, если это не последний аккаунт и лимит не достигнут
                    if not daily_limit_reached and i < len(follow_accounts) - 1:
                        delay = random.uniform(twitter_min_delay, twitter_max_delay)
                        logger.info(
                            f"{wallet} задержка {int(delay)} сек. перед следующей подпиской"
                        )
                        await asyncio.sleep(delay)

                except Exception as e:
                    logger.error(
                        f"{wallet} ошибка при обработке задания для {account_name}: {str(e)}"
                    )

                    # Добавляем задержку после ошибки
                    error_delay = random.uniform(2, 3)
                    logger.info(
                        f"{wallet} задержка {error_delay:.1f} сек. после ошибки"
                    )
                    await asyncio.sleep(error_delay)

                    # Проверяем на ограничения Twitter
                    if (
                        "limit" in str(e).lower()
                        or "unable to follow" in str(e).lower()
                    ):
                        logger.warning(
                            f"{wallet} достигнут лимит Twitter, пропускаем оставшиеся подписки"
                        )
                        daily_limit_reached = True
                        break

                    # Проверяем, может быть проблема с токеном Twitter
                    if any(
                        x in str(e).lower()
                        for x in [
                            "unauthorized",
                            "authentication",
                            "token",
                            "login",
                            "banned",
                        ]
                    ):
                        twitter_errors += 1
                        logger.warning(
                            f"{wallet} возможно проблема с токеном Twitter (ошибка {twitter_errors}/{max_failures})"
                        )

                        # Если достигнут порог ошибок, отмечаем токен как плохой
                        if twitter_errors >= max_failures:
                            await resource_manager.mark_twitter_as_bad(wallet.id)

                            # Если включена автозамена, пробуем заменить токен
                            if (
                                auto_replace
                                and twitter_retry_count < max_twitter_retries - 1
                            ):
                                # Сначала отвязываем текущий Twitter аккаунт
                                await twitter_client.disconnect_twitter()

                                # Затем заменяем токен в БД
                                (
                                    success,
                                    message,
                                ) = await resource_manager.replace_twitter(wallet.id)
                                if success:
                                    logger.info(
                                        f"{wallet} токен Twitter заменен в БД: {message}, выполняю замену на сайте..."
                                    )

                                    # Получаем новый токен из БД
                                    async with Session() as session:
                                        updated_wallet = await session.get(
                                            User, wallet.id
                                        )
                                        if (
                                            updated_wallet
                                            and updated_wallet.twitter_token
                                        ):
                                            # Используем функцию замены токена
                                            replace_success = await twitter_client.replace_twitter_token(
                                                updated_wallet.twitter_token
                                            )
                                            if replace_success:
                                                logger.success(
                                                    f"{wallet} успешно заменен токен Twitter на сайте"
                                                )
                                                wallet.twitter_token = (
                                                    updated_wallet.twitter_token
                                                )
                                                # Увеличиваем счетчик попыток и прерываем текущий цикл подписок
                                                twitter_retry_count += 1
                                                # Закрываем текущий клиент Twitter
                                                await twitter_client.close()
                                                # Переходим к следующей попытке с новым токеном
                                                break
                                            else:
                                                logger.error(
                                                    f"{wallet} не удалось заменить токен Twitter на сайте"
                                                )
                                                # Если не удалось заменить токен на сайте, обновляем токен в объекте
                                                # для следующей попытки, но не используем replace_twitter_token
                                                wallet.twitter_token = (
                                                    updated_wallet.twitter_token
                                                )
                                                twitter_retry_count += 1
                                                await twitter_client.close()
                                                break
                                else:
                                    logger.error(
                                        f"{wallet} не удалось заменить токен Twitter: {message}"
                                    )

            # Закрываем клиент Twitter после обработки всех аккаунтов
            if twitter_client:
                await twitter_client.close()

            # Если был достигнут лимит Twitter или были успешно выполнены все задания, прерываем цикл попыток
            if daily_limit_reached or completed_count == len(follow_accounts):
                break

            # Если был заменен токен и мы перешли к следующей попытке, пропускаем код ниже
            if twitter_retry_count > 0:
                continue

            # Если не было замены токена и не все задания выполнены, но мы прошли по всем аккаунтам,
            # увеличиваем счетчик попыток для следующей итерации
            twitter_retry_count += 1

        except Exception as e:
            logger.error(f"{wallet} ошибка при выполнении Twitter заданий: {str(e)}")

            # Добавляем задержку после ошибки
            error_delay = random.uniform(2, 3)
            logger.info(f"{wallet} задержка {error_delay:.1f} сек. после ошибки")
            await asyncio.sleep(error_delay)

            # Закрываем клиент Twitter, если он был создан
            if twitter_client:
                await twitter_client.close()

            # Проверяем, может быть проблема с токеном Twitter
            if any(
                x in str(e).lower()
                for x in ["unauthorized", "authentication", "token", "login", "banned"]
            ):
                twitter_errors += 1

                # Если достигнут порог ошибок, отмечаем токен как плохой
                if twitter_errors >= max_failures:
                    await resource_manager.mark_twitter_as_bad(wallet.id)

                    # Если включена автозамена, пробуем заменить токен
                    if auto_replace and twitter_retry_count < max_twitter_retries - 1:
                        success, message = await resource_manager.replace_twitter(
                            wallet.id
                        )
                        if success:
                            logger.info(
                                f"{wallet} токен Twitter заменен в БД: {message}, пробуем снова..."
                            )

                            # Обновляем токен в кошельке
                            async with Session() as session:
                                updated_wallet = await session.get(User, wallet.id)
                                if updated_wallet and updated_wallet.twitter_token:
                                    # Сохраняем новый токен для следующей попытки
                                    wallet.twitter_token = updated_wallet.twitter_token
                                    # Увеличиваем счетчик попыток и продолжаем
                                    twitter_retry_count += 1
                                    continue
                        else:
                            logger.error(
                                f"{wallet} не удалось заменить токен Twitter: {message}"
                            )

            # Увеличиваем счетчик попыток
            twitter_retry_count += 1

    # Возвращаем статус успеха и количество выполненных заданий
    return completed_count > 0, completed_count


async def process_wallet_with_specific_quests(
    wallet: User, quest_list, twitter_follows=None
):
    """
    Выполняет указанные задания для одного кошелька с обработкой ошибок ресурсов

    Args:
        wallet: Объект кошелька
        quest_list: Список обычных заданий для выполнения
        twitter_follows: Список Twitter аккаунтов для подписки (опционально)

    Returns:
        Статус успеха
    """
    resource_manager = ResourceManager()
    settings = Settings()
    auto_replace, max_failures = settings.get_resource_settings()

    # Счетчики ошибок
    proxy_errors = 0

    # Для отслеживания необходимости повторной попытки
    retry_with_new_proxy = True
    max_retries = 3
    retry_count = 0

    startup_min, startup_max = settings.get_wallet_startup_delay()
    delay = random.uniform(startup_min, startup_max)
    logger.info(f"Запуск кошелька {wallet} через {int(delay)} сек.")
    await asyncio.sleep(delay)
    # Если twitter_follows не передан, инициализируем пустым списком
    if twitter_follows is None:
        twitter_follows = []

    while retry_with_new_proxy and retry_count < max_retries:
        try:
            # Если это повторная попытка с новым прокси, обновляем данные о кошельке
            if retry_count > 0:
                async with Session() as session:
                    wallet = await session.get(User, wallet.id)
                    if not wallet:
                        logger.error(
                            f"Не удалось получить обновленные данные кошелька с ID {wallet.id}"
                        )
                        return False

            # Определяем, есть ли Twitter задания для выполнения
            has_twitter_tasks = "TwitterFollow" in quest_list or twitter_follows

            logger.info(
                f"Начинаю работу с {wallet} для заданий: {', '.join(quest_list)} "
                + (
                    f"и Twitter подписок: {len(twitter_follows)}"
                    if twitter_follows
                    else ""
                )
                + f" (попытка {retry_count + 1}/{max_retries})"
            )

            # Создаем клиент CampNetwork
            camp_client = CampNetworkClient(user=wallet)

            # Авторизуемся на сайте
            auth_success = await camp_client.login()
            if not auth_success:
                logger.error(f"{wallet} не удалось авторизоваться на CampNetwork")

                # Проверяем, связана ли проблема с прокси
                if (
                    "proxy" in str(auth_success).lower()
                    or "connection" in str(auth_success).lower()
                ):
                    proxy_errors += 1
                    logger.warning(
                        f"{wallet} возможно проблема с прокси (ошибка {proxy_errors}/{max_failures})"
                    )

                    # Добавляем задержку после ошибки
                    error_delay = random.uniform(2, 3)
                    logger.info(
                        f"{wallet} задержка {error_delay:.1f} сек. после ошибки"
                    )
                    await asyncio.sleep(error_delay)

                    # Если достигнут порог ошибок, отмечаем прокси как плохое
                    if proxy_errors >= max_failures:
                        await resource_manager.mark_proxy_as_bad(wallet.id)

                        # Если включена автозамена, пробуем заменить прокси
                        if auto_replace:
                            success, message = await resource_manager.replace_proxy(
                                wallet.id
                            )
                            if success:
                                logger.info(
                                    f"{wallet} прокси заменено: {message}, пробуем снова..."
                                )
                                retry_count += 1
                                continue  # Пробуем снова с новым прокси
                            else:
                                logger.error(
                                    f"{wallet} не удалось заменить прокси: {message}"
                                )
                                retry_with_new_proxy = False  # Прекращаем попытки
                                return False

                # Если проблема не с прокси или нет автозамены, выходим
                retry_with_new_proxy = False
                return False

            # Если авторизация успешна, прекращаем цикл повторных попыток
            retry_with_new_proxy = False

            # Проверяем, включен ли Twitter
            twitter_enabled = (
                settings.twitter_enabled and wallet.twitter_token is not None
            )

            # Разделяем задания на обычные и Twitter
            regular_quests = []

            # Фильтруем задания для Twitter и обычные
            for quest in quest_list:
                if quest != "TwitterFollow":  # Пропускаем общий маркер Twitter задания
                    # Проверяем, что задание существует и не выполнено
                    quest_id = QuestClient.QUEST_IDS.get(quest)
                    if quest_id:
                        async with Session() as session:
                            db = DB(session=session)
                            if not await db.is_quest_completed(wallet.id, quest_id):
                                regular_quests.append(quest)

            # Получаем статистику заданий для отображения
            total_tasks = len(regular_quests) + len(twitter_follows)
            if total_tasks == 0:
                logger.success(f"{wallet} все выбранные задания уже выполнены")
                return True

            logger.info(
                f"{wallet} найдено {len(regular_quests)} обычных заданий и {len(twitter_follows)} Twitter заданий для выполнения"
            )

            # Получаем настройки задержек
            regular_min_delay, regular_max_delay = settings.get_quest_delay()

            # Выполняем обычные задания в случайном порядке
            regular_completed = 0
            if regular_quests:
                # Перемешиваем задания для рандомизации
                random.shuffle(regular_quests)

                logger.info(
                    f"{wallet} выполняю {len(regular_quests)} регулярных заданий"
                )

                for quest_name in regular_quests:
                    try:
                        logger.info(f"{wallet} выполняю задание {quest_name}")
                        result = await camp_client.quest_client.complete_quest(
                            quest_name
                        )

                        if result:
                            logger.success(
                                f"{wallet} успешно выполнено задание {quest_name}"
                            )
                            regular_completed += 1
                        else:
                            logger.warning(
                                f"{wallet} не удалось выполнить задание {quest_name}"
                            )

                            # Добавляем задержку после ошибки
                            error_delay = random.uniform(2, 3)
                            logger.info(
                                f"{wallet} задержка {error_delay:.1f} сек. после ошибки"
                            )
                            await asyncio.sleep(error_delay)

                        # Задержка между заданиями
                        if (
                            quest_name != regular_quests[-1]
                        ):  # Если это не последнее задание
                            delay = random.uniform(regular_min_delay, regular_max_delay)
                            logger.info(
                                f"{wallet} задержка {int(delay)} сек. перед следующим заданием"
                            )
                            await asyncio.sleep(delay)

                    except Exception as e:
                        logger.error(
                            f"{wallet} ошибка при выполнении задания {quest_name}: {str(e)}"
                        )

                        # Добавляем задержку после ошибки
                        error_delay = random.uniform(2, 3)
                        logger.info(
                            f"{wallet} задержка {error_delay:.1f} сек. после ошибки"
                        )
                        await asyncio.sleep(error_delay)

                        # Проверяем, может быть проблема с прокси
                        if (
                            "proxy" in str(e).lower()
                            or "connection" in str(e).lower()
                            or "timeout" in str(e).lower()
                        ):
                            proxy_errors += 1
                            logger.warning(
                                f"{wallet} возможно проблема с прокси (ошибка {proxy_errors}/{max_failures})"
                            )

                            # Если достигнут порог ошибок, отмечаем прокси как плохое
                            if proxy_errors >= max_failures:
                                await resource_manager.mark_proxy_as_bad(wallet.id)

                        await asyncio.sleep(regular_min_delay)
                        continue

            # Выполняем Twitter задания, если они есть и Twitter включен
            twitter_completed_count = 0
            if twitter_enabled and has_twitter_tasks and twitter_follows:
                # Добавляем задержку перед Twitter заданиями, если были обычные задания
                if regular_quests:
                    twitter_delay = random.uniform(regular_min_delay, regular_max_delay)
                    logger.info(
                        f"{wallet} задержка {int(twitter_delay)} сек. перед началом Twitter заданий"
                    )
                    await asyncio.sleep(twitter_delay)

                # Выполняем Twitter задания через общую функцию
                twitter_result, twitter_completed_count = await process_twitter_tasks(
                    wallet=wallet,
                    camp_client=camp_client,
                    resource_manager=resource_manager,
                    settings=settings,
                    follow_accounts=twitter_follows,
                )

                if twitter_result:
                    logger.success(
                        f"{wallet} успешно выполнено {twitter_completed_count} из {len(twitter_follows)} Twitter заданий"
                    )
                else:
                    logger.warning(
                        f"{wallet} Twitter задания выполнены частично: {twitter_completed_count} из {len(twitter_follows)}"
                    )

            # Получаем список выполненных квестов для проверки
            async with Session() as session:
                db = DB(session=session)
                final_completed_quests = await db.get_completed_quests(wallet.id)

            # Выводим итоговые результаты
            completed_count = regular_completed + twitter_completed_count
            total_requested = len(regular_quests) + len(twitter_follows)

            logger.success(
                f"{wallet} выполнение заданий завершено. "
                f"Выполнено всего: {completed_count}/{total_requested} запрошенных заданий"
            )
            logger.info(
                f"{wallet} успешно выполнено обычных заданий: {regular_completed} из {len(regular_quests)}"
            )
            logger.info(
                f"{wallet} успешно выполнено Twitter заданий: {twitter_completed_count} из {len(twitter_follows)}"
            )

            # Считаем задание успешным, если выполнено хотя бы одно задание
            return completed_count > 0

        except Exception as e:
            logger.error(f"{wallet} ошибка при обработке: {str(e)}")

            # Добавляем задержку после ошибки
            error_delay = random.uniform(2, 3)
            logger.info(f"{wallet} задержка {error_delay:.1f} сек. после ошибки")
            await asyncio.sleep(error_delay)

            # Проверяем, может быть проблема с прокси
            if (
                "proxy" in str(e).lower()
                or "connection" in str(e).lower()
                or "timeout" in str(e).lower()
            ):
                proxy_errors += 1
                logger.warning(
                    f"{wallet} возможно проблема с прокси (ошибка {proxy_errors}/{max_failures})"
                )

                # Если достигнут порог ошибок, отмечаем прокси как плохое
                if proxy_errors >= max_failures:
                    await resource_manager.mark_proxy_as_bad(wallet.id)

                    # Если включена автозамена, пробуем заменить прокси
                    if auto_replace:
                        success, message = await resource_manager.replace_proxy(
                            wallet.id
                        )
                        if success:
                            logger.info(
                                f"{wallet} прокси заменено: {message}, пробуем снова..."
                            )
                            retry_count += 1
                            continue  # Пробуем снова с новым прокси
                        else:
                            logger.error(
                                f"{wallet} не удалось заменить прокси: {message}"
                            )
                else:
                    await asyncio.sleep(10)
                    retry_count += 1
                    continue

            # Если проблема не с прокси или не удалось заменить прокси
            return False

    # Если исчерпаны все попытки
    if retry_count >= max_retries:
        logger.error(f"{wallet} исчерпаны все {max_retries} попытки с заменой прокси")

    return False


async def handle_onchain(user: User):
    settings = Settings()
    startup_min, startup_max = settings.get_wallet_startup_delay()
    delay = random.uniform(startup_min, startup_max)
    logger.info(f"Запуск кошелька {user} через {int(delay)} сек.")
    await asyncio.sleep(delay)
    client = create_client(
        private_key=user.private_key, network="camp", proxy=user.proxy
    )

    resource_manager = ResourceManager()
    proxy_errors = 0
    auto_replace, max_failures = settings.get_resource_settings()
    balance = 0
    for _ in range(max_failures):
        try:
            balance = await client.wallet.balance()
            await client.close()
            break
        except Exception as e:
            if "proxy" in str(e).lower() or "connection" in str(e).lower():
                proxy_errors += 1
                logger.warning(f"{user} возможно проблема с прокси")

                # Добавляем задержку после ошибки
                error_delay = random.uniform(2, 3)
                logger.info(f"{user} задержка {error_delay:.1f} сек. после ошибки")
                await asyncio.sleep(error_delay)

                # Если достигнут порог ошибок, отмечаем прокси как плохое
                if proxy_errors >= 3:
                    await resource_manager.mark_proxy_as_bad(user.id)

                    # Если включена автозамена, пробуем заменить прокси
                    if auto_replace:
                        success, message = await resource_manager.replace_proxy(user.id)
                        if success:
                            logger.info(
                                f"{user} прокси заменено: {message}, пробуем снова..."
                            )
                            continue  # Пробуем снова с новым прокси
                        else:
                            logger.error(
                                f"{user} не удалось заменить прокси: {message}"
                            )
                            return False
    if balance == 0 and settings.use_faucet:
        faucet = await handle_faucet(user=user)
        if not faucet:
            return False
    if balance == 0 and not settings.use_faucet:
        logger.warning(
            f"{user} don't have balance for mint and use_faucet disabled in settings"
        )
        return False
    onchain = CampOnchain(user=user)
    await onchain.handle_mint()
    logger.info(f"{user} Onchain Work Done!")
    return True


async def handle_faucet(user: User, make_delay: bool = False):
    settings = Settings()
    if make_delay:
        startup_min, startup_max = settings.get_wallet_startup_delay()
        delay = random.uniform(startup_min, startup_max)
        logger.info(f"Запуск кошелька {user} через {int(delay)} сек.")
        await asyncio.sleep(delay)

    client = Client(
        private_key=user.private_key,
        network=Networks.Ethereum,
        proxy=user.proxy,
        check_proxy=False,
    )

    resource_manager = ResourceManager()
    proxy_errors = 0
    auto_replace, max_failures = settings.get_resource_settings()
    nonce = 0
    for _ in range(max_failures):
        try:
            nonce = await client.wallet.nonce()
            break
        except Exception as e:
            if "proxy" in str(e).lower() or "connection" in str(e).lower():
                proxy_errors += 1
                logger.warning(f"{user} возможно проблема с прокси")

                # Добавляем задержку после ошибки
                error_delay = random.uniform(2, 3)
                logger.info(f"{user} задержка {error_delay:.1f} сек. после ошибки")
                await asyncio.sleep(error_delay)

                # Если достигнут порог ошибок, отмечаем прокси как плохое
                if proxy_errors >= 3:
                    await resource_manager.mark_proxy_as_bad(user.id)

                    # Если включена автозамена, пробуем заменить прокси
                    if auto_replace:
                        success, message = await resource_manager.replace_proxy(user.id)
                        if success:
                            logger.info(
                                f"{user} прокси заменено: {message}, пробуем снова..."
                            )
                            continue  # Пробуем снова с новым прокси
                        else:
                            logger.error(
                                f"{user} не удалось заменить прокси: {message}"
                            )
                            return False

    if not SOLVECAPTCHA_API_KEY:
        logger.error(f"{user} put SolveCaptcha Api Key in .env file")
        return False
    if nonce < 3:
        logger.warning(f"{user} don't have 3 transactions in ETH Mainnet skip account")
        return False
    if (
        user.faucet_last_claim
        and (datetime.utcnow() - user.faucet_last_claim).total_seconds() < 24 * 60 * 60
    ):
        logger.warning(f"{user} already claimed faucet in last 24 hours")
        return False

    faucet = Faucet(user=user, api_key=SOLVECAPTCHA_API_KEY)
    for _ in range(10):
        try:
            claim = await faucet.claim_tokens()
            if claim:
                async with Session() as session:
                    db = DB(session=session)
                    await db.update_last_faucet_claim(user_id=user.id)
                return True
        except RateLimitError:
            logger.warning(f"{user} already claim faucet in last 24 hours")
            async with Session() as session:
                db = DB(session=session)
                await db.update_last_faucet_claim(user_id=user.id)
            return False
        except CaptchaUnsolvableError:
            logger.warning(f"{user} get capctha unsolvable try again")
            continue
        except FaucetError as e:
            logger.error(f"{user} have error with Faucet claim try again {_}/10 {e}")

            # Проверяем, связана ли проблема с прокси
            logger.error(f"{user} have error with Faucet claim try again {_}/10 {e}")
            continue
        except Exception as e:
            logger.error(f"{user} have unknown error with Faucet {e}")
            return False


async def start_onchain():
    try:
        # Получаем список кошельков из базы данных
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()

        if not all_wallets:
            logger.error("Нет кошельков в базе данных. Сначала импортируйте кошельки.")
            return

        # Определяем диапазон кошельков для обработки из настроек
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]

        # Отображаем информацию о количестве кошельков для обработки
        logger.info(f"Найдено {len(all_wallets)} кошельков")
        logger.info(
            f"Будет обработано {len(wallets)} кошельков (с {wallet_start + 1} по {wallet_start + len(wallets)})"
        )

        # Перемешиваем кошельки для рандомизации порядка
        random.shuffle(wallets)

        # Получаем настройки задержки между запуском аккаунтов

        # Создаем задачи для всех кошельков
        tasks = []
        for i, wallet in enumerate(wallets):
            # Добавляем случайную задержку между запуском обработки кошельков

            # Создаем задачу для обработки кошелька
            task = asyncio.create_task(handle_onchain(wallet))
            tasks.append(task)

        # Если нет задач, выходим
        if not tasks:
            logger.warning("Нет кошельков для обработки")
            return

        # Запускаем все задачи
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Анализируем результаты
        success_count = sum(1 for result in results if result is True)
        error_count = sum(
            1 for result in results if isinstance(result, Exception) or result is False
        )

        logger.info(
            f"Обработка завершена: успешно {success_count}, с ошибками {error_count}"
        )

    except Exception as e:
        logger.error(f"Ошибка при выполнении заданий для всех кошельков: {str(e)}")


async def all_faucet_claim():
    try:
        # Получаем список кошельков из базы данных
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()

        if not all_wallets:
            logger.error("Нет кошельков в базе данных. Сначала импортируйте кошельки.")
            return

        # Определяем диапазон кошельков для обработки из настроек
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]

        # Отображаем информацию о количестве кошельков для обработки
        logger.info(f"Найдено {len(all_wallets)} кошельков")
        logger.info(
            f"Будет обработано {len(wallets)} кошельков (с {wallet_start + 1} по {wallet_start + len(wallets)})"
        )

        # Перемешиваем кошельки для рандомизации порядка
        random.shuffle(wallets)

        # Получаем настройки задержки между запуском аккаунтов

        # Создаем задачи для всех кошельков
        tasks = []
        for i, wallet in enumerate(wallets):
            # Добавляем случайную задержку между запуском обработки кошельков

            # Создаем задачу для обработки кошелька
            task = asyncio.create_task(handle_faucet(wallet, make_delay=True))
            tasks.append(task)

        # Если нет задач, выходим
        if not tasks:
            logger.warning("Нет кошельков для обработки")
            return

        # Запускаем все задачи
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Анализируем результаты
        success_count = sum(1 for result in results if result is True)
        error_count = sum(
            1 for result in results if isinstance(result, Exception) or result is False
        )

        logger.info(
            f"Обработка завершена: успешно {success_count}, с ошибками {error_count}"
        )

    except Exception as e:
        logger.error(f"Ошибка при выполнении заданий для всех кошельков: {str(e)}")


async def complete_all_wallets_quests():
    """Выполняет задания для всех кошельков"""
    try:
        # Получаем список кошельков из базы данных
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()

        if not all_wallets:
            logger.error("Нет кошельков в базе данных. Сначала импортируйте кошельки.")
            return

        # Определяем диапазон кошельков для обработки из настроек
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]

        # Отображаем информацию о количестве кошельков для обработки
        logger.info(f"Найдено {len(all_wallets)} кошельков")
        logger.info(
            f"Будет обработано {len(wallets)} кошельков (с {wallet_start + 1} по {wallet_start + len(wallets)})"
        )

        # Перемешиваем кошельки для рандомизации порядка
        random.shuffle(wallets)

        # Получаем настройки задержки между запуском аккаунтов

        # Создаем задачи для всех кошельков
        tasks = []
        for i, wallet in enumerate(wallets):
            # Добавляем случайную задержку между запуском обработки кошельков

            # Создаем задачу для обработки кошелька
            task = asyncio.create_task(process_wallet(wallet))
            tasks.append(task)

        # Если нет задач, выходим
        if not tasks:
            logger.warning("Нет кошельков для обработки")
            return

        # Запускаем все задачи
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Анализируем результаты
        success_count = sum(1 for result in results if result is True)
        error_count = sum(
            1 for result in results if isinstance(result, Exception) or result is False
        )

        logger.info(
            f"Обработка завершена: успешно {success_count}, с ошибками {error_count}"
        )

    except Exception as e:
        logger.error(f"Ошибка при выполнении заданий для всех кошельков: {str(e)}")


async def complete_specific_quests():
    """Выполняет указанные задания для всех кошельков с учетом настроек"""
    try:
        # Получаем список кошельков из базы данных
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()

        if not all_wallets:
            logger.error("Нет кошельков в базе данных. Сначала импортируйте кошельки.")
            return

        # Определяем диапазон кошельков для обработки из настроек
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]

        # Перемешиваем кошельки для рандомизации
        random.shuffle(wallets)

        logger.info(f"Найдено {len(all_wallets)} кошельков")
        logger.info(
            f"Будет обработано {len(wallets)} кошельков (с {wallet_start + 1} по {wallet_start + len(wallets)})"
        )

        # Получаем список доступных обычных заданий
        quests = list(QuestClient.QUEST_IDS.keys())

        # Добавляем Twitter задания с более понятными названиями
        if settings.twitter_enabled:
            twitter_accounts = TwitterClient.TWITTER_QUESTS_MAP.get("Follow", {})
            for account, quest_id in twitter_accounts.items():
                quests.append(f"Twitter Follow: @{account}")

        print("\n=== Доступные задания ===")
        for i, quest_name in enumerate(quests, 1):
            print(f"{i}. {quest_name}")

        print("\nВведите номера заданий через запятую (или 'all' для всех):")
        quest_input = input("> ").strip()

        if quest_input.lower() == "all":
            selected_quests = quests
        else:
            try:
                # Парсим введенные номера
                quest_numbers = [
                    int(num.strip()) for num in quest_input.split(",") if num.strip()
                ]
                selected_quests = [
                    quests[num - 1] for num in quest_numbers if 1 <= num <= len(quests)
                ]

                if not selected_quests:
                    logger.error("Не выбрано ни одного задания")
                    return
            except (ValueError, IndexError):
                logger.error(
                    f"Некорректный ввод. Номер задания должен быть от 1 до {len(quests)}"
                )
                return

        logger.info(f"Выбраны задания: {', '.join(selected_quests)}")

        # Преобразуем названия Twitter Follow заданий в обычный формат для обработки
        processed_quests = []
        twitter_follows = []

        for quest in selected_quests:
            if quest.startswith("Twitter Follow: @"):
                account_name = quest.replace("Twitter Follow: @", "")
                twitter_follows.append(account_name)
            else:
                processed_quests.append(quest)

        # Если выбраны Twitter задания, добавляем общий маркер TwitterFollow
        if twitter_follows:
            processed_quests.append("TwitterFollow")

        # Получаем настройки задержки между запуском аккаунтов

        # Создаем задачи для всех кошельков
        tasks = []
        for i, wallet in enumerate(wallets):
            # Добавляем случайную задержку между запуском обработки кошельков

            # Создаем задачу для обработки кошелька
            task = asyncio.create_task(
                process_wallet_with_specific_quests(
                    wallet, processed_quests, twitter_follows
                )
            )
            tasks.append(task)

        # Если нет задач, выходим
        if not tasks:
            logger.warning("Нет кошельков для обработки")
            return

        # Запускаем все задачи
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Анализируем результаты
        success_count = sum(1 for result in results if result is True)
        error_count = sum(
            1 for result in results if isinstance(result, Exception) or result is False
        )

        logger.info(
            f"Обработка завершена: успешно {success_count}, с ошибками {error_count}"
        )

    except Exception as e:
        logger.error(f"Ошибка при выполнении заданий для всех кошельков: {str(e)}")


async def get_wallets_stats():
    """Получает статистику по всем кошелькам из базы данных, включая Twitter интеграцию и статус блокировки"""
    try:
        # Получаем все кошельки из базы данных
        async with Session() as session:
            db = DB(session=session)
            wallets = await db.get_all_wallets()

        if not wallets:
            logger.error("Нет кошельков в базе данных")
            return

        logger.info(f"Получаю статистику для {len(wallets)} кошельков")

        # Создаем словарь для обратного поиска названий по ID
        quest_names_by_id = {
            quest_id: quest_name
            for quest_name, quest_id in QuestClient.QUEST_IDS.items()
        }

        # Добавляем Twitter задания в словарь
        twitter_quests = {}
        for account_name, quest_id in TwitterClient.TWITTER_QUESTS_MAP.get(
            "Follow", {}
        ).items():
            quest_names_by_id[quest_id] = f"Twitter Follow: @{account_name}"
            twitter_quests[quest_id] = account_name

        # Получаем общее количество заданий (включая Twitter)
        total_quests_count = len(QuestClient.QUEST_IDS) + len(twitter_quests)

        # Создаем словарь для хранения статистики
        stats = {}

        # Для каждого кошелька получаем статистику из БД
        for wallet in wallets:
            try:
                # Проверяем статус блокировки
                if wallet.account_blocked == 1:
                    stats[wallet.public_key] = {
                        "blocked": True,
                        "message": "Attention: Аккаунт заблокирован",
                    }
                    continue

                # Получаем список выполненных квестов
                completed_quests_ids = (
                    wallet.completed_quests.split(",")
                    if wallet.completed_quests and wallet.completed_quests != ""
                    else []
                )
                completed_count = (
                    len(completed_quests_ids) if completed_quests_ids else 0
                )

                # Получаем названия выполненных заданий по их ID
                completed_quest_names = []

                # Обычные квесты
                regular_completed = 0
                twitter_completed = 0

                for quest_id in completed_quests_ids:
                    quest_name = quest_names_by_id.get(quest_id)

                    if quest_name:
                        completed_quest_names.append(quest_name)

                        # Определяем тип задания и обновляем счетчики
                        if quest_id in twitter_quests:
                            twitter_completed += 1
                        else:
                            regular_completed += 1
                    else:
                        completed_quest_names.append(f"Unknown ({quest_id})")

                # Добавляем информацию о Twitter
                twitter_status = "Подключен" if wallet.twitter_token else "Не подключен"
                twitter_health = (
                    "OK"
                    if wallet.twitter_status == "OK"
                    else "Blocked"
                    if wallet.twitter_status == "BAD"
                    else "Bad"
                )

                stats[wallet.public_key] = {
                    "blocked": False,
                    "completed_count": completed_count,
                    "total_count": total_quests_count,
                    "regular_completed": regular_completed,
                    "twitter_completed": twitter_completed,
                    "regular_total": len(QuestClient.QUEST_IDS),
                    "twitter_total": len(twitter_quests),
                    "completed_quests": completed_quest_names,
                    "twitter_status": twitter_status,
                    "twitter_health": twitter_health,
                }

            except Exception as e:
                stats[wallet.public_key] = {"error": str(e)}

        # Выводим статистику
        print("\n=== Статистика кошельков ===")

        # Сортируем кошельки по количеству выполненных заданий (по убыванию)
        sorted_wallets = sorted(
            stats.keys(),
            key=lambda k: stats[k].get("completed_count", 0)
            if "error" not in stats[k] and not stats[k].get("blocked", False)
            else -1,
            reverse=True,
        )

        for wallet_key in sorted_wallets:
            wallet_stats = stats[wallet_key]

            if "error" in wallet_stats:
                logger.warning(f"{wallet_key}: {wallet_stats['error']}")
            elif wallet_stats.get("blocked", False):
                logger.warning(f"{wallet_key}: {wallet_stats['message']}")
            else:
                percent = int(
                    (wallet_stats["completed_count"] / wallet_stats["total_count"])
                    * 100
                )
                status_color = (
                    "green" if percent == 100 else "yellow" if percent > 50 else "red"
                )

                # Сокращаем адрес кошелька для компактности
                short_key = f"{wallet_key[:6]}...{wallet_key[-4:]}"

                # Полная статистика с разбивкой на обычные и Twitter задания
                logger.info(
                    f"{short_key}: {wallet_stats['completed_count']}/{wallet_stats['total_count']} заданий ({percent}%), "
                    + f"Обычные: {wallet_stats['regular_completed']}/{wallet_stats['regular_total']}, "
                    + f"Twitter: {wallet_stats['twitter_completed']}/{wallet_stats['twitter_total']}, "
                    + f"Twitter: {wallet_stats['twitter_status']} ({wallet_stats['twitter_health']})"
                )

        # Выводим общую статистику
        total_wallets = len(stats)
        blocked_wallets = sum(
            1 for wallet in stats.values() if wallet.get("blocked", False)
        )
        active_wallets = total_wallets - blocked_wallets
        completed_wallets = sum(
            1
            for wallet in stats.values()
            if "error" not in wallet
            and not wallet.get("blocked", False)
            and wallet["completed_count"] == wallet["total_count"]
        )
        average_completion = (
            sum(
                wallet["completed_count"]
                for wallet in stats.values()
                if "error" not in wallet and not wallet.get("blocked", False)
            )
            / active_wallets
            if active_wallets > 0
            else 0
        )

        # Отдельная статистика по обычным и Twitter заданиям
        regular_average = (
            sum(
                wallet["regular_completed"]
                for wallet in stats.values()
                if "error" not in wallet and not wallet.get("blocked", False)
            )
            / active_wallets
            if active_wallets > 0
            else 0
        )
        twitter_average = (
            sum(
                wallet["twitter_completed"]
                for wallet in stats.values()
                if "error" not in wallet and not wallet.get("blocked", False)
            )
            / active_wallets
            if active_wallets > 0
            else 0
        )

        # Статистика подключения Twitter
        twitter_connected = sum(
            1
            for wallet in stats.values()
            if "error" not in wallet
            and not wallet.get("blocked", False)
            and wallet["twitter_status"] == "Подключен"
        )
        twitter_healthy = sum(
            1
            for wallet in stats.values()
            if "error" not in wallet
            and not wallet.get("blocked", False)
            and wallet["twitter_health"] == "OK"
        )

        print("\n=== Общая статистика ===")
        print(f"Всего кошельков: {total_wallets}")
        print(
            f"Заблокировано: {blocked_wallets} ({int((blocked_wallets / total_wallets) * 100)}%)"
        )
        print(
            f"Активно: {active_wallets} ({int((active_wallets / total_wallets) * 100)}%)"
        )
        print(
            f"Завершено полностью: {completed_wallets} ({int((completed_wallets / active_wallets) * 100) if active_wallets else 0}%)"
        )
        print(
            f"Среднее количество выполненных заданий: {average_completion:.1f} из {total_quests_count}"
        )
        print(
            f"  - Обычные задания: {regular_average:.1f} из {len(QuestClient.QUEST_IDS)}"
        )
        print(f"  - Twitter задания: {twitter_average:.1f} из {len(twitter_quests)}")
        print(
            f"Twitter статус: подключено {twitter_connected} из {active_wallets} ({int((twitter_connected / active_wallets) * 100) if active_wallets else 0}%)"
        )
        print(
            f"Twitter здоровье: в порядке {twitter_healthy} из {twitter_connected} ({int((twitter_healthy / twitter_connected) * 100) if twitter_connected else 0}%)"
        )

        return stats

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}")
        return {}


async def check_wallet_blocked(
    wallet: User, resource_manager: ResourceManager
) -> Tuple[bool, str]:
    """
    Проверяет, заблокирован ли кошелек, пытаясь выполнить авторизацию.

    Args:
        wallet: Объект кошелька
        resource_manager: Объект ResourceManager для управления ресурсами

    Returns:
        Tuple[bool, str]: (Статус проверки, Сообщение об ошибке или статусе)
    """
    if wallet.account_blocked:
        return False, f"{wallet} account blocked and marked in database"

    startup_min, startup_max = settings.get_wallet_startup_delay()
    delay = random.uniform(startup_min, startup_max)
    logger.info(f"Запуск кошелька {wallet} через {int(delay)} сек.")
    await asyncio.sleep(delay)

    try:
        # Создаем клиент CampNetwork
        camp_client = CampNetworkClient(user=wallet)

        # Пытаемся авторизоваться
        auth_success, response = await camp_client.login()

        if auth_success:
            return True, f"{wallet} successfully authorized, not blocked"

        # Проверяем, связана ли ошибка с блокировкой кошелька
        if "WALLET_ADDRESS_BLOCKED".lower() in str(response).lower():
            logger.error(f"{wallet} account blocked")
            await resource_manager.mark_wallet_as_blocked(wallet.id)
            return False, f"{wallet} account blocked and marked in database"

        return False, f"{wallet} authorization failed for unknown reason"

    except Exception as e:
        logger.error(f"{wallet} error during block check: {str(e)}")

        # Проверяем, связана ли ошибка с блокировкой кошелька
        if "WALLET_ADDRESS_BLOCKED".lower() in str(e).lower():
            await resource_manager.mark_wallet_as_blocked(wallet.id)
            return False, f"{wallet} account blocked and marked in database"

        return False, f"{wallet} error during authorization check: {str(e)}"


async def check_all_wallets_blocked():
    """Проверяет все кошельки на наличие блокировки"""
    try:
        # Получаем список кошельков из базы данных
        async with Session() as session:
            db = DB(session=session)
            all_wallets = await db.get_all_wallets()

        if not all_wallets:
            logger.error("Нет кошельков в базе данных. Сначала импортируйте кошельки.")
            return

        # Инициализируем настройки и менеджер ресурсов
        settings = Settings()
        resource_manager = ResourceManager()

        # Определяем диапазон кошельков для проверки из настроек
        wallet_start, wallet_end = settings.get_wallet_range()
        if wallet_end > 0 and wallet_end <= len(all_wallets):
            wallets = all_wallets[wallet_start:wallet_end]
        else:
            wallets = all_wallets[wallet_start:]

        # Отображаем информацию о количестве кошельков для проверки
        logger.info(f"Найдено {len(all_wallets)} кошельков")
        logger.info(
            f"Будет проверено {len(wallets)} кошельков (с {wallet_start + 1} по {wallet_start + len(wallets)})"
        )

        # Перемешиваем кошельки для рандомизации порядка
        random.shuffle(wallets)

        # Создаем задачи для всех кошельков
        tasks = []
        for i, wallet in enumerate(wallets):
            # Создаем задачу для проверки кошелька
            task = asyncio.create_task(check_wallet_blocked(wallet, resource_manager))
            tasks.append(task)

        # Если нет задач, выходим
        if not tasks:
            logger.warning("Нет кошельков для проверки")
            return

        # Запускаем все задачи
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Анализируем результаты
        success_count = sum(
            1 for result in results if isinstance(result, Tuple) and result[0] is True
        )

        blocked_count = sum(
            1
            for result in results
            if isinstance(result, Tuple)
            and result[0] is False
            and "account blocked and marked in database" in str(result[1].lower())
        )
        error_count = sum(
            1
            for result in results
            if isinstance(result, Exception)
            or (
                isinstance(result, Tuple)
                and result[0] is False
                and "account blocked and marked in database"
                not in str(result[1].lower())
            )
        )

        logger.info(
            f"Проверка завершена: не заблокированы {success_count}, заблокированы {blocked_count}, ошибки {error_count}"
        )

    except Exception as e:
        logger.error(f"Ошибка при проверке всех кошельков на блокировку: {str(e)}")
