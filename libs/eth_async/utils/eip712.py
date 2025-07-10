from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
from typing import Dict, Any


async def sign_permit2_message(client, permit_data: Dict[str, Any]) -> str:
    """
    Подписывает Permit2 сообщение для Uniswap
    """
    try:
        # Берем types из API и добавляем недостающий EIP712Domain
        types = permit_data['types'].copy()
        types["EIP712Domain"] = [
            {"name": "name", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"}
        ]
        
        # Формируем EIP-712 сообщение с полным контролем над каждым полем
        message = {
            "types": types,
            "domain": {
                "name": str(permit_data['domain']['name']),  # "Permit2"
                "chainId": str(permit_data['domain']['chainId']),  # "8453" как строка
                "verifyingContract": str(permit_data['domain']['verifyingContract']).lower()  # "0x000000000022D473030F116dDEE9F6B43aC78BA3"
            },
            "primaryType": "PermitSingle",
            "message": {
                "details": {
                    "token": str(permit_data['values']['details']['token']).lower(),  # "0x6985884c4392d348587b19cb9eaaf157f13271cd"
                    "amount": str(permit_data['values']['details']['amount']),  # "1461501637330902918203684832716283019655932542975"
                    "expiration": str(permit_data['values']['details']['expiration']),  # "1752230520" 
                    "nonce": str(permit_data['values']['details']['nonce'])  # "0"
                },
                "spender": str(permit_data['values']['spender']).lower(),  # "0x6ff5693b99212da76ad316178a184ab56d299b43"
                "sigDeadline": str(permit_data['values']['sigDeadline'])  # "1749640320"
            }
        }

        message = {
            "types": permit_data['types'],
            "domain": permit_data['domain'],
            "primaryType": "PermitSingle",
            "message": permit_data['values']
        }
        
        
        signable_message = encode_typed_data(full_message=message)
        signed_message = Account.sign_message(signable_message, client.account.key.hex())
        
        # Возвращаем hex без 0x
        return '0x' + signed_message.signature.hex()
        
    except Exception as e:
        raise Exception(f"Failed to sign Permit2: {e}")
