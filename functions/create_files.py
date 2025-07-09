import os
import csv

from libs.eth_async.utils.utils import update_dict
from libs.eth_async.utils.files import touch, write_json, read_json

from data import config


def create_files():
    touch(path=config.FILES_DIR)

    if not os.path.exists(config.REF_CODES_FILE):
        with open(config.REF_CODES_FILE, "w") as f:
            pass

    if not os.path.exists(config.PRIVATE_FILE):
        with open(config.PRIVATE_FILE, "w") as f:
            pass

    if not os.path.exists(config.PROXY_FILE):
        with open(config.PROXY_FILE, "w") as f:
            pass
    if not os.path.exists(config.TWITTER_FILE):
        with open(config.TWITTER_FILE, "w") as f:
            pass

    # Создаем файлы для резервных ресурсов
    if not os.path.exists(config.RESERVE_PROXY_FILE):
        with open(config.RESERVE_PROXY_FILE, "w") as f:
            pass
    if not os.path.exists(config.RESERVE_TWITTER_FILE):
        with open(config.RESERVE_TWITTER_FILE, "w") as f:
            pass

    try:
        current_settings: dict | None = read_json(path=config.SETTINGS_FILE)
    except Exception:
        current_settings = {}

    settings = {
        "use_ssl": True,
        "use_faucet": False,
        # Twitter настройки
        "twitter": {
            "enabled": True,
            "delay_between_actions": {
                "min": 120,  # секунды
                "max": 180,  # секунды
            },
            "delay_between_quests": {
                "min": 300,  # секунды
                "max": 600,  # секунды
            },
        },
        # Общие настройки
        "quests": {
            "delay_between_quests": {
                "min": 20,  # секунды
                "max": 40,  # секунды
            }
        },
        "referrals": {
            "use_random_from_db": True,  # Использовать случайные коды из БД
            "use_only_file_codes": False,  # Использовать только коды из файла
        },
        # Настройки запуска аккаунтов
        "wallets": {
            "range": {
                "start": 0,  # начальный индекс
                "end": 0,  # конечный индекс (0 = все)
            },
            "startup_delay": {
                "min": 0,  # секунды
                "max": 7200,  # секунды
            },
        },
        # Настройки ресурсов
        "resources": {
            "auto_replace": True,  # Автоматическая замена плохих ресурсов
            "max_failures": 3,  # Максимальное количество ошибок до отметки ресурса как плохого
        },
    }
    write_json(
        path=config.SETTINGS_FILE,
        obj=update_dict(modifiable=current_settings, template=settings),
        indent=2,
    )


create_files()
