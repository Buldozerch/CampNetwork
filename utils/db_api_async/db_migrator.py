import os
from pathlib import Path
from loguru import logger
from alembic.config import Config
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import OperationalError


async def check_and_migrate_db():
    """
    Проверяет структуру БД и выполняет необходимые миграции с использованием Alembic.
    """
    try:
        logger.info("Проверка структуры базы данных...")

        # Определяем путь к БД и файлу alembic.ini
        db_path = Path("./files/wallets.db")
        alembic_cfg_path = Path("alembic.ini")

        # Проверяем, существует ли файл alembic.ini
        if not alembic_cfg_path.exists():
            logger.error("Файл alembic.ini не найден. Убедитесь, что Alembic настроен.")
            return False

        # Проверяем, существует ли база данных
        if not db_path.exists():
            logger.info(
                "База данных не существует, создание новой. Миграции будут применены автоматически."
            )
            return await _apply_migrations(alembic_cfg_path)

        # Подключаемся к базе данных для проверки структуры
        engine = create_engine(f"sqlite:///{db_path}")
        inspector = inspect(engine)

        # Проверяем наличие таблицы alembic_version
        has_alembic_version = inspector.has_table("alembic_version")

        # Проверяем наличие столбцов ref_code и account_blocked в таблице campnetwork
        required_columns = ["ref_code", "account_blocked", "faucet_last_claim"]
        if inspector.has_table("campnetwork"):
            columns = [col["name"] for col in inspector.get_columns("campnetwork")]
            missing_columns = [col for col in required_columns if col not in columns]
            all_columns_present = len(missing_columns) == 0
        else:
            logger.warning("Таблица campnetwork не найдена. Миграции создадут её.")
            missing_columns = required_columns
            all_columns_present = False

        # Загружаем конфигурацию Alembic
        alembic_cfg = Config(alembic_cfg_path)
        alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

        # Проверяем текущую версию миграции
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_revision = context.get_current_revision()

        script = ScriptDirectory.from_config(alembic_cfg)
        head_revision = script.get_current_head()

        if not has_alembic_version:
            logger.warning(
                "Таблица alembic_version отсутствует. Пометка БД как актуальная."
            )
            command.stamp(alembic_cfg, "head")
            if all_columns_present:
                logger.success(
                    "Все требуемые столбцы (ref_code, account_blocked) уже существуют, миграция не требуется."
                )
                return True
            return await _apply_migrations(alembic_cfg)

        if current_revision == head_revision:
            logger.info("База данных уже на последней версии миграции.")
            if all_columns_present:
                logger.success(
                    "Все требуемые столбцы (ref_code, account_blocked, faucet_last_claim) присутствуют, всё в порядке."
                )
                return True
            else:
                logger.warning(
                    f"Отсутствуют столбцы: {', '.join(missing_columns)}. Требуется новая миграция."
                )
                return await _apply_migrations(alembic_cfg)

        # Применяем миграции, если БД не на последней версии
        logger.info("База данных устарела, применение миграций...")
        return await _apply_migrations(alembic_cfg)

    except Exception as e:
        logger.error(f"Ошибка при проверке или миграции базы данных: {str(e)}")
        return False


async def _apply_migrations(alembic_cfg):
    """
    Применяет миграции Alembic.
    """
    try:
        command.upgrade(alembic_cfg, "head")
        logger.success("Миграция базы данных успешно выполнена.")
        return True
    except Exception as e:
        logger.error(f"Ошибка при выполнении миграции: {str(e)}")
        if "duplicate column name" in str(e).lower():
            logger.warning(
                "Один или несколько столбцов уже существуют. Пометка БД как актуальная."
            )
            command.stamp(alembic_cfg, "head")
            return True
        return False
