import os
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

if getattr(sys, "frozen", False):
    ROOT_DIR = Path(sys.executable).parent.absolute()
else:
    ROOT_DIR = Path(__file__).parent.parent.absolute()

FILES_DIR = os.path.join(ROOT_DIR, "files")
ABIS_DIR = os.path.join(ROOT_DIR, "abis")

CAPMONSTER_API_KEY = os.getenv("CAPMONSTER_API_KEY")
SOLVECAPTCHA_API_KEY = os.getenv("SOLVECAPTCHA_API_KEY")

REF_CODES_FILE = os.path.join(FILES_DIR, "ref_codes.txt")
PROXY_FILE = os.path.join(FILES_DIR, "proxy.txt")
PRIVATE_FILE = os.path.join(FILES_DIR, "private.txt")
TWITTER_FILE = os.path.join(FILES_DIR, "twitter.txt")

# Добавляем пути к резервным файлам
RESERVE_PROXY_FILE = os.path.join(FILES_DIR, "reserve_proxy.txt")
RESERVE_TWITTER_FILE = os.path.join(FILES_DIR, "reserve_twitter.txt")

SETTINGS_FILE = os.path.join(FILES_DIR, "settings.json")
ACTUAL_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
ACTUAL_FOLLOWS_TWITTER = [
    "MySphereAI",
    "pets_ww",
    "blocsocial_",
    "campnetworkxyz",
    "clustersxyz",
    "PictographsNFT",
    "arcoin_official",
    "entertainm_io",
    "bleetz_io",
    "xade_xyz",
    "summitx_finance",
    "OrbiMatrix",
    "rapier_xyz",
    "olympicsdotfun",
    "weepingplebs",
    "TheMetakraft",
    "thepixudi",
    "ScorePlay_xyz",
    "tokentails",
    "rarible",
    "ConftApp",
    "arkivist_ai",
    "cheb_inc",
    "awanalab",
    "onbd_art",
    "Fantasy_cristal",
    "PanenkaFC90",
    "xross__road",
    "reblapp",
    "merv_wtf",
    "merv_toon",
    "chronicle_ww",
    "StoryChain_ai",
]

ACTUAL_NFT_MINT = [
    "base_camp",
    "aura",
    "cope_ville",
    "climb",
    "pictographs",
    "tokentails",
]
LOG_FILE = os.path.join(FILES_DIR, "log.log")
ERRORS_FILE = os.path.join(FILES_DIR, "errors.log")

logger.add(ERRORS_FILE, level="ERROR")
logger.add(LOG_FILE, level="INFO")
