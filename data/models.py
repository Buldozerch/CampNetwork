from libs.eth_async.utils.files import read_json
from libs.eth_async.classes import AutoRepr, Singleton
from data.config import SETTINGS_FILE, ACTUAL_FOLLOWS_TWITTER

class Settings(Singleton, AutoRepr):
    def __init__(self):
        json_data = read_json(path=SETTINGS_FILE)
        self.use_ssl = json_data.get("use_ssl", True)
        self.twitter_enabled = json_data.get('twitter', {}).get('enabled', True)
        
        self.twitter_delay_actions_min = json_data.get('twitter', {}).get('delay_between_actions', {}).get('min', 60)
        self.twitter_delay_actions_max = json_data.get('twitter', {}).get('delay_between_actions', {}).get('max', 180)
        
        self.twitter_delay_quests_min = json_data.get('twitter', {}).get('delay_between_quests', {}).get('min', 300)
        self.twitter_delay_quests_max = json_data.get('twitter', {}).get('delay_between_quests', {}).get('max', 600)
        
        # Twitter аккаунты для подписки
        self.twitter_follow_accounts = ACTUAL_FOLLOWS_TWITTER
        
        # Настройки обычных квестов
        self.quest_delay_min = json_data.get('quests', {}).get('delay_between_quests', {}).get('min', 20)
        self.quest_delay_max = json_data.get('quests', {}).get('delay_between_quests', {}).get('max', 40)
        
        # Настройки кошельков
        self.wallet_range_start = json_data.get('wallets', {}).get('range', {}).get('start', 0)
        self.wallet_range_end = json_data.get('wallets', {}).get('range', {}).get('end', 0)
        
        self.wallet_startup_delay_min = json_data.get('wallets', {}).get('startup_delay', {}).get('min', 5)
        self.wallet_startup_delay_max = json_data.get('wallets', {}).get('startup_delay', {}).get('max', 15)

        self.referrals_use_random_from_db = json_data.get('referrals', {}).get('use_random_from_db', True)
        self.referrals_use_only_file_codes = json_data.get('referrals', {}).get('use_only_file_codes', False)       
        # Настройки ресурсов
        self.resources_auto_replace = json_data.get('resources', {}).get('auto_replace', True)
        self.resources_max_failures = json_data.get('resources', {}).get('max_failures', 3)
    
    def get_use_ssl(self):
        return self.use_ssl

    def get_twitter_action_delay(self) -> tuple:
        """Возвращает диапазон задержки между действиями в Twitter"""
        return self.twitter_delay_actions_min, self.twitter_delay_actions_max
    
    def get_twitter_quest_delay(self) -> tuple:
        """Возвращает диапазон задержки между заданиями в Twitter"""
        return self.twitter_delay_quests_min, self.twitter_delay_quests_max
    
    def get_quest_delay(self) -> tuple:
        """Возвращает диапазон задержки между обычными заданиями"""
        return self.quest_delay_min, self.quest_delay_max
    
    def get_wallet_startup_delay(self) -> tuple:
        """Возвращает диапазон задержки между запуском аккаунтов"""
        return self.wallet_startup_delay_min, self.wallet_startup_delay_max
    
    def get_wallet_range(self) -> tuple:
        """Возвращает диапазон индексов кошельков для обработки"""
        return self.wallet_range_start, self.wallet_range_end
    
    def get_resource_settings(self) -> tuple:
        """Возвращает настройки управления ресурсами"""
        return self.resources_auto_replace, self.resources_max_failures

    def get_referral_settings(self) -> tuple:
        """Возвращает настройки реферальных кодов"""
        return self.referrals_use_random_from_db, self.referrals_use_only_file_codes
