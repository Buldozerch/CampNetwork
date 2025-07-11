from libs.eth_async.utils.files import read_json
from libs.eth_async.data.models import RawContract
from libs.eth_async.classes import Singleton

from data.config import ABIS_DIR


class Contracts(Singleton):
    """Упрощенная конфигурация контрактов"""

    BASE_CAMP = RawContract(
        title="BASE_CAMP",
        address="0x72E2160e41C467D7437cAe4d76Ac4FdC2D475e68",
        abi=read_json(path=(ABIS_DIR, "rarible.json")),
    )

    AURA = RawContract(
        title="AURA",
        address="0x42b978985F1b0676f7224ddBCa76D67A5D4a4dc3",
        abi=read_json(path=(ABIS_DIR, "rarible.json")),
    )

    STICKY_PLEB = RawContract(
        title="STICKY_PLEB",
        address="0x0d7516f4A6823F6F11a8F1C292E5DF1A6fF5775b",
        abi=read_json(path=(ABIS_DIR, "rarible.json")),
    )

    CLIMB = RawContract(
        title="CLIMB",
        address="0x3785F882e823F3436Df2e669Fc9f7490525f47d4",
        abi=read_json(path=(ABIS_DIR, "rarible.json")),
    )

    PICTOGRAPHS = RawContract(
        title="PICTOGRAPHS",
        address="0x37Cbfa07386dD09297575e6C699fe45611AC12FE",
        abi=read_json(path=(ABIS_DIR, "rarible.json")),
    )
    TOKEN_TAILS = RawContract(
        title="TOKEN_TAILS",
        address="0xa0D4687483F049c53e6EC8cBCbc0332C74180168",
        abi=read_json(path=(ABIS_DIR, "tokenTails.json")),
    )
