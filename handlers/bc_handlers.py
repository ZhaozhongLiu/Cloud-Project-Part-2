#!/usr/bin/env python3
"""
This module (bc_handlers.py) bridges your P2P network peers with an on-chain Solidity contract. In brief, it:
- Connects to a Hardhat local blockchain.
- Loads the ABI and address of a deployed Solidity contract.
- Provides functions to add strings to the contract and fetch all stored strings.
- Implements handlers for P2P BC requests and responses.
- Uses the Web3.py library to interact with the Ethereum blockchain.
- Uses the dotenv library to load environment variables.
- Uses the json library to handle JSON data.
- Uses the os and pathlib libraries to manage file paths and environment variables.
"""

from __future__ import annotations
import json
import os
import pathlib
from typing import Any, List
from dotenv import load_dotenv
from web3 import Web3
from web3.contract import Contract

# Load environment variables
load_dotenv()
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CHAIN_ID = int(os.getenv("CHAIN_ID", 31337))

if not PRIVATE_KEY:
    raise RuntimeError("PRIVATE_KEY is not set. Please add it to .env")

# Connect to Hardhat network
w3 = Web3(Web3.HTTPProvider(RPC_URL))
if not w3.is_connected():
    raise RuntimeError(f"Cannot connect to node at {RPC_URL}")

ACCOUNT = w3.eth.account.from_key(PRIVATE_KEY).address

# Load contract ABI and address
ARTIFACT_PATH = pathlib.Path(__file__).resolve().parent.parent / \
    "artifacts/contracts/StringChain.sol/StringChain.json"

if ARTIFACT_PATH.exists():
    with open(ARTIFACT_PATH) as f:
        abi = json.load(f)["abi"]
else:
    abi = [
        {
            "inputs": [{"internalType": "string", "name": "data", "type": "string"}],
            "name": "addData",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        },
        {
            "inputs": [],
            "name": "getAll",
            "outputs": [{"internalType":"string[]", "name":"", "type":"string[]"}],
            "stateMutability": "view",
            "type": "function"
        }
    ]

ADDRESS_FILE = pathlib.Path("stringchain.addr")
if not ADDRESS_FILE.exists():
    raise FileNotFoundError("stringchain.addr not found. Deploy the contract first.")

CONTRACT_ADDRESS = ADDRESS_FILE.read_text().strip()
contract: Contract = w3.eth.contract(address=CONTRACT_ADDRESS, abi=abi)

def _fill_fee_fields(tx: dict[str, Any]) -> None:
    """Ensure tx dict has gas and gas price fields."""
    if not tx.get("gas"):
        tx["gas"] = w3.eth.estimate_gas(tx)
    if "gasPrice" not in tx and "maxFeePerGas" not in tx:
        tx["gasPrice"] = w3.eth.gas_price or Web3.toWei(1, "gwei")

def _send_tx(tx: dict[str, Any]) -> None:
    """Sign and send a raw transaction."""
    _fill_fee_fields(tx)
    signed = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    raw_tx = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction", signed)
    tx_hash = w3.eth.send_raw_transaction(raw_tx)
    w3.eth.wait_for_transaction_receipt(tx_hash)

def add_onchain(text: str) -> None:
    """Add a string to the on-chain contract."""
    tx = contract.functions.addData(text).build_transaction({
        "from": ACCOUNT,
        "nonce": w3.eth.get_transaction_count(ACCOUNT),
        "chainId": CHAIN_ID
    })
    _send_tx(tx)

def fetch_all() -> List[str]:
    """Retrieve all stored strings from the contract."""
    return contract.functions.getAll().call()

def bc_request_handler(peer, conn, msg: str) -> None:
    """Handle incoming P2P BC requests."""
    cmd, *rest = msg.split(maxsplit=1)
    cmd = cmd.upper()
    payload = rest[0] if rest else ""
    try:
        if cmd == "STORE":
            add_onchain(payload)
            response = {"type": "ACK", "msg": "stored"}
        elif cmd == "FETCH":
            response = {"type": "ALL", "data": fetch_all()}
        else:
            response = {"type": "ERR", "msg": f"Unknown command {cmd}"}
    except Exception as e:
        print(f"[BC-RX] Request failed: {e}")
        response = {"type": "ERR", "msg": str(e)}

    if conn:
        conn.senddata("BCRS", json.dumps(response))

def bc_response_handler(_peer, msg: str) -> None:
    """Process BC responses from peers."""
    try:
        data = json.loads(msg)
    except json.JSONDecodeError:
        print(f"[BC-RX] Non-JSON response: {msg}")
        return

    typ = data.get("type")
    if typ == "ACK":
        print("✓ Data stored on-chain")
    elif typ == "ALL":
        print("→ On-chain data:", data.get("data"))
    else:
        print("⚠️ Error:", data.get("msg"))
