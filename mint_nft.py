# from web3 import Web3
# from dotenv import load_dotenv
# import os
# import json

# load_dotenv()

# w3 = Web3(Web3.HTTPProvider(os.getenv("WEB3_PROVIDER")))
# private_key = os.getenv("PRIVATE_KEY")
# wallet_address = os.getenv("WALLET_ADDRESS")
# contract_address = os.getenv("CONTRACT_ADDRESS")

# with open("nft_abi.json") as f:
#     abi = json.load(f)

# contract = w3.eth.contract(address=contract_address, abi=abi)

# def mint_trade_nft(to_address, token_uri):
#     nonce = w3.eth.get_transaction_count(wallet_address)

#     txn = contract.functions.safeMint(to_address, token_uri).build_transaction({
#         'from': wallet_address,
#         'nonce': nonce,
#         'gas': 300000,
#         'gasPrice': w3.to_wei('50', 'gwei')
#     })

#     signed_txn = w3.eth.account.sign_transaction(txn, private_key=private_key)
#     tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)

#     return w3.to_hex(tx_hash)
