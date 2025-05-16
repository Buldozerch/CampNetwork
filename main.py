from functions.create_files import create_files
from functions.activity import (add_wallets_db, complete_all_wallets_quests, 
                               get_wallets_stats, complete_specific_quests)

from sqlalchemy import text
from website.resource_manager import ResourceManager
import asyncio
import os
import sys
from loguru import logger
from data.models import Settings
from data import config
import rich
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Создаем консоль для красивого вывода
console = Console()

def print_logo():
    """Выводит логотип программы"""
    text = Text()
    text.append("╔═══════════════════════════════════════════╗\n", style="cyan")
    text.append("║              ", style="cyan")
    text.append("CAMP NETWORK FARMER", style="bold white")
    text.append("              ║\n", style="cyan")
    text.append("╠═══════════════════════════════════════════╣\n", style="cyan")
    text.append("║ ", style="cyan")
    text.append("GitHub: https://github.com/Buldozerch", style="white")
    text.append("       ║\n", style="cyan")
    text.append("║ ", style="cyan")
    text.append("Channel: https://t.me/buldozercode", style="white")
    text.append("         ║\n", style="cyan")
    text.append("╚═══════════════════════════════════════════╝", style="cyan")
    console.print(text)
    console.print()


async def option_update_settings():
    """Обновляет настройки программы"""
    settings = Settings()
    try:
        # Выводим текущие настройки
        console.print("\n[bold cyan]Текущие настройки:[/]")
        
        # Twitter настройки
        console.print("\n[bold]1. Twitter настройки:[/]")
        console.print(f"   Использовать Twitter: {'[green]Да[/]' if settings.twitter_enabled else '[red]Нет[/]'}")
        console.print(f"   Задержка между действиями в Twitter: {settings.twitter_delay_actions_min}-{settings.twitter_delay_actions_max} секунд")
        console.print(f"   Задержка между заданиями Twitter: {settings.twitter_delay_quests_min}-{settings.twitter_delay_quests_max} секунд")
        
        # Общие настройки
        console.print("\n[bold]2. Общие настройки:[/]")
        console.print(f"   Задержка между заданиями: {settings.quest_delay_min}-{settings.quest_delay_max} секунд")
        
        # Настройки кошельков
        console.print("\n[bold]3. Настройки кошельков:[/]")
        wallet_end = "[green]все[/]" if settings.wallet_range_end == 0 else str(settings.wallet_range_end)
        console.print(f"   Диапазон кошельков: {settings.wallet_range_start}-{wallet_end}")
        console.print(f"   Задержка между запуском аккаунтов: {settings.wallet_startup_delay_min}-{settings.wallet_startup_delay_max} секунд")
        
        # Настройки ресурсов
        console.print("\n[bold]4. Настройки ресурсов:[/]")
        console.print(f"   Автоматическая замена ресурсов: {'[green]Да[/]' if settings.resources_auto_replace else '[red]Нет[/]'}")
        console.print(f"   Максимальное количество ошибок: {settings.resources_max_failures}")
        
        # Запрашиваем, какие настройки обновить
        console.print("\n[bold cyan]Выберите настройки для обновления:[/]")
        console.print("1. Twitter настройки")
        console.print("2. Общие настройки")
        console.print("3. Настройки кошельков")
        console.print("4. Настройки ресурсов")
        console.print("5. Все настройки")
        console.print("6. Назад")
        
        choice = int(input("> "))
        
        if choice == 6:
            return
        
        # Получаем текущие настройки из json файла
        from libs.eth_async.utils.files import read_json, write_json
        from data.config import SETTINGS_FILE
        
        current_settings = read_json(path=SETTINGS_FILE)
        
        # Обновляем Twitter настройки
        if choice in [1, 5]:
            console.print("\n[bold]Обновление Twitter настроек:[/]")
            
            # Использовать Twitter
            use_twitter = input("Использовать Twitter (y/n) [текущее: " + 
                             ("y" if settings.twitter_enabled else "n") + "]: ").strip().lower()
            if use_twitter in ["y", "n"]:
                current_settings["twitter"]["enabled"] = (use_twitter == "y")
            
            # Задержка между действиями
            action_delay_min = input(f"Минимальная задержка между действиями (секунды) [текущее: {settings.twitter_delay_actions_min}]: ").strip()
            if action_delay_min.isdigit() and int(action_delay_min) > 0:
                current_settings["twitter"]["delay_between_actions"]["min"] = int(action_delay_min)
                
            action_delay_max = input(f"Максимальная задержка между действиями (секунды) [текущее: {settings.twitter_delay_actions_max}]: ").strip()
            if action_delay_max.isdigit() and int(action_delay_max) > int(current_settings["twitter"]["delay_between_actions"]["min"]):
                current_settings["twitter"]["delay_between_actions"]["max"] = int(action_delay_max)
            
            # Задержка между заданиями
            quest_delay_min = input(f"Минимальная задержка между заданиями Twitter (секунды) [текущее: {settings.twitter_delay_quests_min}]: ").strip()
            if quest_delay_min.isdigit() and int(quest_delay_min) > 0:
                current_settings["twitter"]["delay_between_quests"]["min"] = int(quest_delay_min)
                
            quest_delay_max = input(f"Максимальная задержка между заданиями Twitter (секунды) [текущее: {settings.twitter_delay_quests_max}]: ").strip()
            if quest_delay_max.isdigit() and int(quest_delay_max) > int(current_settings["twitter"]["delay_between_quests"]["min"]):
                current_settings["twitter"]["delay_between_quests"]["max"] = int(quest_delay_max)
        
        # Обновляем общие настройки
        if choice in [2, 5]:
            console.print("\n[bold]Обновление общих настроек:[/]")
            
            # Задержка между заданиями
            quest_delay_min = input(f"Минимальная задержка между заданиями (секунды) [текущее: {settings.quest_delay_min}]: ").strip()
            if quest_delay_min.isdigit() and int(quest_delay_min) > 0:
                current_settings["quests"]["delay_between_quests"]["min"] = int(quest_delay_min)
                
            quest_delay_max = input(f"Максимальная задержка между заданиями (секунды) [текущее: {settings.quest_delay_max}]: ").strip()
            if quest_delay_max.isdigit() and int(quest_delay_max) > int(current_settings["quests"]["delay_between_quests"]["min"]):
                current_settings["quests"]["delay_between_quests"]["max"] = int(quest_delay_max)
        
        # Обновляем настройки кошельков
        if choice in [3, 5]:
            console.print("\n[bold]Обновление настроек кошельков:[/]")
            
            # Диапазон кошельков
            wallet_start = input(f"Начальный индекс кошелька [текущее: {settings.wallet_range_start}]: ").strip()
            if wallet_start.isdigit() and int(wallet_start) >= 0:
                current_settings["wallets"]["range"]["start"] = int(wallet_start)
                
            wallet_end = input(f"Конечный индекс кошелька (0 = все) [текущее: {settings.wallet_range_end}]: ").strip()
            if wallet_end.isdigit() and int(wallet_end) >= 0:
                current_settings["wallets"]["range"]["end"] = int(wallet_end)
            
            # Задержка между запуском аккаунтов
            startup_delay_min = input(f"Минимальная задержка между запуском аккаунтов (секунды) [текущее: {settings.wallet_startup_delay_min}]: ").strip()
            if startup_delay_min.isdigit() and int(startup_delay_min) >= 0:
                current_settings["wallets"]["startup_delay"]["min"] = int(startup_delay_min)
                
            startup_delay_max = input(f"Максимальная задержка между запуском аккаунтов (секунды) [текущее: {settings.wallet_startup_delay_max}]: ").strip()
            if startup_delay_max.isdigit() and int(startup_delay_max) > int(current_settings["wallets"]["startup_delay"]["min"]):
                current_settings["wallets"]["startup_delay"]["max"] = int(startup_delay_max)
        
        # Обновляем настройки ресурсов
        if choice in [4, 5]:
            console.print("\n[bold]Обновление настроек ресурсов:[/]")
            
            # Создаем раздел ресурсов, если его еще нет
            if "resources" not in current_settings:
                current_settings["resources"] = {
                    "auto_replace": True,
                    "max_failures": 3
                }
            
            # Автоматическая замена
            auto_replace = input(f"Автоматическая замена ресурсов (y/n) [текущее: {'y' if settings.resources_auto_replace else 'n'}]: ").strip().lower()
            if auto_replace in ["y", "n"]:
                current_settings["resources"]["auto_replace"] = (auto_replace == "y")
            
            # Максимальное количество ошибок
            max_failures = input(f"Максимальное количество ошибок [текущее: {settings.resources_max_failures}]: ").strip()
            if max_failures.isdigit() and int(max_failures) > 0:
                current_settings["resources"]["max_failures"] = int(max_failures)
        
        # Сохраняем обновленные настройки
        write_json(path=SETTINGS_FILE, obj=current_settings, indent=2)
        console.print("\n[bold green]Настройки успешно обновлены[/]")
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении настроек: {str(e)}")
        console.print(f"\n[bold red]Ошибка при обновлении настроек: {str(e)}[/]")

async def option_manage_resources():
    """Управление ресурсами (прокси, токены Twitter)"""
    try:
        
        resource_manager = ResourceManager()
        
        while True:
            # Получаем статистику плохих ресурсов
            bad_proxies_count, bad_twitter_count = await resource_manager.get_bad_resources_stats()
            
            # Получаем количество доступных резервных ресурсов
            reserve_proxies = resource_manager._load_from_file(config.RESERVE_PROXY_FILE)
            reserve_twitter = resource_manager._load_from_file(config.RESERVE_TWITTER_FILE)
            
            console.print("\n[bold cyan]Управление ресурсами[/]")
            console.print(f"Обнаружено [red]{bad_proxies_count}[/] плохих прокси и [red]{bad_twitter_count}[/] плохих токенов Twitter")
            console.print(f"Доступно [green]{len(reserve_proxies)}[/] резервных прокси и [green]{len(reserve_twitter)}[/] резервных токенов Twitter")
            
            # Меню
            menu = Table(show_header=False, box=None)
            menu.add_column("Option", style="cyan")
            menu.add_column("Description", style="white")
            
            menu.add_row("1)", "Показать плохие прокси")
            menu.add_row("2)", "Показать плохие токены Twitter")
            menu.add_row("3)", "Заменить плохие прокси")
            menu.add_row("4)", "Заменить плохие токены Twitter")
            menu.add_row("5)", "Заменить все плохие ресурсы")
            menu.add_row("6)", "Назад")
            
            console.print(menu)
            
            choice = input("\n> ")
            
            if choice == "1":
                # Показать плохие прокси
                console.print("\n[bold]Плохие прокси:[/]")
                
                bad_proxies = await resource_manager.get_bad_proxies()
                
                if bad_proxies:
                    for wallet in bad_proxies:
                        short_key = f"{wallet.public_key[:6]}...{wallet.public_key[-4:]}"
                        console.print(f" - ID: {wallet.id}, Кошелек: {short_key}, Прокси: {wallet.proxy}")
                else:
                    console.print("[green]Нет плохих прокси[/]")
                
                input("\nНажмите Enter для продолжения...")
                
            elif choice == "2":
                # Показать плохие токены Twitter
                console.print("\n[bold]Плохие токены Twitter:[/]")
                
                bad_twitter = await resource_manager.get_bad_twitter()
                
                if bad_twitter:
                    for wallet in bad_twitter:
                        short_key = f"{wallet.public_key[:6]}...{wallet.public_key[-4:]}"
                        console.print(f" - ID: {wallet.id}, Кошелек: {short_key}")
                else:
                    console.print("[green]Нет плохих токенов Twitter[/]")
                
                input("\nНажмите Enter для продолжения...")
                
            elif choice == "3":
                # Заменить плохие прокси
                console.print("\n[bold]Замена плохих прокси...[/]")
                
                if len(reserve_proxies) == 0:
                    console.print("[red]Ошибка:[/] Нет доступных резервных прокси в файле reserve_proxy.txt")
                    input("\nНажмите Enter для продолжения...")
                    continue
                
                if bad_proxies_count == 0:
                    console.print("[green]Нет плохих прокси для замены[/]")
                    input("\nНажмите Enter для продолжения...")
                    continue
                
                if len(reserve_proxies) < bad_proxies_count:
                    console.print(f"[yellow]Внимание:[/] Доступно только {len(reserve_proxies)} резервных прокси, при этом плохих - {bad_proxies_count}")
                
                # Запрашиваем подтверждение
                confirm = input("Продолжить с заменой? (y/n): ").strip().lower()
                if confirm != 'y':
                    continue
                
                # Выполняем замену
                replaced, total = await resource_manager.replace_all_bad_proxies()
                
                console.print(f"[green]Заменено {replaced} из {total} плохих прокси[/]")
                input("\nНажмите Enter для продолжения...")
                
            elif choice == "4":
                # Заменить плохие токены Twitter
                console.print("\n[bold]Замена плохих токенов Twitter...[/]")
                
                if len(reserve_twitter) == 0:
                    console.print("[red]Ошибка:[/] Нет доступных резервных токенов Twitter в файле reserve_twitter.txt")
                    input("\nНажмите Enter для продолжения...")
                    continue
                
                if bad_twitter_count == 0:
                    console.print("[green]Нет плохих токенов Twitter для замены[/]")
                    input("\nНажмите Enter для продолжения...")
                    continue
                
                if len(reserve_twitter) < bad_twitter_count:
                    console.print(f"[yellow]Внимание:[/] Доступно только {len(reserve_twitter)} резервных токенов Twitter, при этом плохих - {bad_twitter_count}")
                
                # Запрашиваем подтверждение
                confirm = input("Продолжить с заменой? (y/n): ").strip().lower()
                if confirm != 'y':
                    continue
                
                # Выполняем замену
                replaced, total = await resource_manager.replace_all_bad_twitter()
                
                console.print(f"[green]Заменено {replaced} из {total} плохих токенов Twitter[/]")
                input("\nНажмите Enter для продолжения...")
                
            elif choice == "5":
                # Заменить все плохие ресурсы
                console.print("\n[bold]Замена всех плохих ресурсов...[/]")
                
                if len(reserve_proxies) == 0 and len(reserve_twitter) == 0:
                    console.print("[red]Ошибка:[/] Нет доступных резервных ресурсов")
                    input("\nНажмите Enter для продолжения...")
                    continue
                
                if bad_proxies_count == 0 and bad_twitter_count == 0:
                    console.print("[green]Нет плохих ресурсов для замены[/]")
                    input("\nНажмите Enter для продолжения...")
                    continue
                
                # Выводим предупреждения
                if len(reserve_proxies) < bad_proxies_count:
                    console.print(f"[yellow]Внимание:[/] Доступно только {len(reserve_proxies)} резервных прокси, при этом плохих - {bad_proxies_count}")
                
                if len(reserve_twitter) < bad_twitter_count:
                    console.print(f"[yellow]Внимание:[/] Доступно только {len(reserve_twitter)} резервных токенов Twitter, при этом плохих - {bad_twitter_count}")
                
                # Запрашиваем подтверждение
                confirm = input("Продолжить с заменой? (y/n): ").strip().lower()
                if confirm != 'y':
                    continue
                
                # Выполняем замену всех ресурсов
                proxies_replaced, proxies_total = await resource_manager.replace_all_bad_proxies()
                twitter_replaced, twitter_total = await resource_manager.replace_all_bad_twitter()
                
                console.print(f"[green]Заменено {proxies_replaced} из {proxies_total} плохих прокси[/]")
                console.print(f"[green]Заменено {twitter_replaced} из {twitter_total} плохих токенов Twitter[/]")
                input("\nНажмите Enter для продолжения...")
                
            elif choice == "6":
                # Назад
                return
                
            else:
                console.print("\n[bold yellow]Неверный выбор. Пожалуйста, выберите действие от 1 до 6.[/]")
                input("Нажмите Enter для продолжения...")
                
    except Exception as e:
        logger.error(f"Ошибка при управлении ресурсами: {str(e)}")
        console.print(f"\n[bold red]Ошибка при управлении ресурсами: {str(e)}[/]")
        input("Нажмите Enter для продолжения...")

def print_menu():
    """Выводит меню программы"""
    menu = Table(show_header=False, box=None)
    menu.add_column("Option", style="cyan")
    menu.add_column("Description", style="white")
    
    menu.add_row("1)", "Импорт кошельков в базу данных")
    menu.add_row("2)", "Выполнить все задания")
    menu.add_row("3)", "Выполнить выбранные задания")
    menu.add_row("4)", "Показать статистику")
    menu.add_row("5)", "Управление ресурсами")  # Новый пункт меню
    menu.add_row("6)", "Настройки")
    menu.add_row("7)", "Выход")
    
    console.print(menu)

async def main():
    """Основная функция программы"""
    # Инициализация файлов и базы данных
    create_files()
    from utils.db_api_async.db_init import init_db
    await init_db()
    
    
    while True:
        os.system('cls' if os.name == 'nt' else 'clear')  # Очищаем консоль
        print_logo()
        print_menu()
        
        try:
            action = input("\n> ")
            
            if action == "1":
                # Импорт кошельков
                console.print("\n[bold cyan]Импорт кошельков в базу данных...[/]")
                await add_wallets_db()
                console.print("[bold green]Импорт завершен. Нажмите Enter для продолжения...[/]")
                input()
                
            elif action == "2":
                # Выполнить все задания
                console.print("\n[bold cyan]Выполнение всех заданий...[/]")
                await complete_all_wallets_quests()
                console.print("[bold green]Выполнение заданий завершено. Нажмите Enter для продолжения...[/]")
                input()
                
            elif action == "3":
                # Выполнить выбранные задания
                console.print("\n[bold cyan]Выполнение выбранных заданий...[/]")
                await complete_specific_quests()
                console.print("[bold green]Выполнение заданий завершено. Нажмите Enter для продолжения...[/]")
                input()
                
            elif action == "4":
                # Показать статистику
                console.print("\n[bold cyan]Получение статистики...[/]")
                await get_wallets_stats()
                console.print("[bold green]Нажмите Enter для продолжения...[/]")
                input()
                
            elif action == "5":
                # Управление ресурсами (новая опция)
                await option_manage_resources()
                
            elif action == "6":
                # Настройки
                await option_update_settings()
                
            elif action == "7":
                # Выход
                console.print("\n[bold cyan]Выход из программы. До свидания![/]")
                sys.exit(0)
                
            else:
                console.print("\n[bold yellow]Неверный выбор. Пожалуйста, выберите действие от 1 до 7.[/]")
                input("Нажмите Enter для продолжения...")
                
        except KeyboardInterrupt:
            console.print("\n[bold cyan]Программа прервана пользователем. До свидания![/]")
            sys.exit(0)
        except ValueError as err:
            logger.error(f'Ошибка ввода данных: {err}')
            console.print(f"\n[bold red]Ошибка ввода данных: {err}[/]")
            input("Нажмите Enter для продолжения...")
        except Exception as e:
            logger.error(f'Неожиданная ошибка: {e}')
            console.print(f"\n[bold red]Неожиданная ошибка: {e}[/]")
            input("Нажмите Enter для продолжения...")

if __name__ == "__main__":
    try:
        # # Настраиваем логи
        # logger.remove()  # Удаляем стандартный обработчик
        # # Добавляем только необходимые уровни логирования
        # logger.add(
        #     "files/errors.log", 
        #     level="ERROR", 
        #     format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
        # )
        # logger.add(
        #     "files/log.log", 
        #     level="INFO",
        #     format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        #     filter=lambda record: record["level"].name == "INFO" or record["level"].name == "SUCCESS"
        # )
        
        # Запускаем программу
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[bold cyan]Программа завершена![/]")
        sys.exit(0)
