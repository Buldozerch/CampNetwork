import os
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv
load_dotenv() 

if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).parent.absolute()
else:
    ROOT_DIR = Path(__file__).parent.parent.absolute()

FILES_DIR = os.path.join(ROOT_DIR, 'files')

CAPMONSTER_API_KEY = os.getenv('CAPMONSTER_API_KEY')

REF_CODES_FILE = os.path.join(FILES_DIR, 'ref_codes.txt')
PROXY_FILE = os.path.join(FILES_DIR, 'proxy.txt')
PRIVATE_FILE = os.path.join(FILES_DIR, 'private.txt')
TWITTER_FILE = os.path.join(FILES_DIR, 'twitter.txt')

# Добавляем пути к резервным файлам
RESERVE_PROXY_FILE = os.path.join(FILES_DIR, 'reserve_proxy.txt')
RESERVE_TWITTER_FILE = os.path.join(FILES_DIR, 'reserve_twitter.txt')

SETTINGS_FILE = os.path.join(FILES_DIR, 'settings.json')
ACTUAL_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
ACTUAL_FOLLOWS_TWITTER = [
                        "StoryChain_ai",
                        "tokentails",
                        "PanenkaFC90",
                        "ScorePlay_xyz",
                        "wideworlds_ai",
                        "pets_ww",
                        "chronicle_ww",
                        "PictographsNFT",
                        "entertainm_io",
                        "bleetz_io",
                        "RewardedTV_",
                        "Fantasy_cristal",
                        "belgranofantasy",
                        "awanalab",
                        "arcoin_official",
                        "TheMetakraft",
                        "summitx_finance",
                        "thepixudi",
                        "clustersxyz",
                        "JukebloxDapp",
                        "campnetworkxyz",
                        "hitmakrr",
                        "merv_wtf",
                        "merv_toon",
    
]

LOG_FILE = os.path.join(FILES_DIR, 'log.log')
ERRORS_FILE = os.path.join(FILES_DIR, 'errors.log')

logger.add(ERRORS_FILE, level='ERROR')
logger.add(LOG_FILE, level='INFO')
