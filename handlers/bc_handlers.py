"""
def bc_request_handler(peer, conn, msgdata):
    print(f"[{peer.myid}] Received BC request with data: {msgdata}")
    result = f"Processed({msgdata})"
    conn.senddata("BCRS", result)  # BCRS = Blockchain Response

def bc_response_handler(peer, msgdata):
    print(f"[{peer.myid}] Received BC response: {msgdata}")
"""
#!/usr/bin/env python3
"""
bc_handlers.py – 区块链节点的 P2P 处理器（升级版）
----------------------------------------------------
• 支持 pending 数据池、挖矿、链校验
• 通过 BCRQ/BCRS 消息在 P2P 网络传播
• 难度默认为 5 个前导 0，可自行调节

BCRQ 命令
~~~~~~~~~
GET         → 返回整条链
MINE        → 打包 pending 数据并挖新区块
TXN <json>  → 向 pending 池追加一条数据
SYNC        → 返回链长（内部广播）

BCRS 响应类型
~~~~~~~~~~~~~
CHAIN, NEW_BLOCK, ACK_TXN, LEN, ERROR
"""
from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any, Dict, List

# --------------------------------------------------------------------------- #
# 区块链核心实现
# --------------------------------------------------------------------------- #
class Blockchain:
    """极简区块链：支持数据交易池 & PoW."""

    def __init__(self, *, difficulty: int = 5) -> None:
        self.chain: List[Dict[str, Any]] = []
        self.pending: List[Any] = []              # 待上链数据
        self.difficulty = max(1, difficulty)
        self.create_block(proof=1, previous_hash="0", data=["genesis"])

    # ----------------------- 对外 API ----------------------- #
    def add_data(self, data: Any) -> None:
        """把数据加入待打包池（lazy 上链）。"""
        self.pending.append(data)

    def mine_block(self) -> Dict[str, Any]:
        """打包 pending 数据并挖新区块，返回区块 dict。"""
        last_proof = self.chain[-1]["proof"]
        proof = self._proof_of_work(last_proof)
        prev_hash = self._hash_block(self.chain[-1])
        new_block = self.create_block(proof, prev_hash,
                                      self.pending or ["<empty>"])
        self.pending.clear()
        return new_block

    def get_chain(self) -> List[Dict[str, Any]]:
        return self.chain

    # ----------------------- 内部实现 ----------------------- #
    def create_block(self, proof: int, previous_hash: str,
                     data: List[Any]) -> Dict[str, Any]:
        block = {
            "index": len(self.chain) + 1,
            "timestamp": str(datetime.datetime.utcnow()),
            "proof": proof,
            "previous_hash": previous_hash,
            "data": data,
        }
        self.chain.append(block)
        return block

    def _proof_of_work(self, previous_proof: int) -> int:
        new_proof = 1
        target = "0" * self.difficulty
        while True:
            calc = hashlib.sha256(
                f"{new_proof**2 - previous_proof**2}".encode()
            ).hexdigest()
            if calc.startswith(target):
                return new_proof
            new_proof += 1

    def _hash_block(self, block: Dict[str, Any]) -> str:
        return hashlib.sha256(
            json.dumps(block, sort_keys=True).encode()
        ).hexdigest()

    def is_valid(self) -> bool:
        for i in range(1, len(self.chain)):
            curr, prev = self.chain[i], self.chain[i - 1]
            if curr["previous_hash"] != self._hash_block(prev):
                return False
            if not self._hash_block(curr).startswith("0" * self.difficulty):
                return False
        return True


# 单实例（每个 BC 节点只需一个）
blockchain = Blockchain(difficulty=5)

# --------------------------------------------------------------------------- #
# P2P 消息处理器
# --------------------------------------------------------------------------- #
def bc_request_handler(peer, conn, msgdata: str) -> None:
    """服务器端 dispatcher —— 注册到 peer.add_handler('BCRQ', ...)"""
    parts = msgdata.split(maxsplit=1)
    cmd = parts[0].upper()
    payload = parts[1] if len(parts) == 2 else ""

    if cmd == "GET":                      # 拉链
        reply = {"type": "CHAIN", "data": blockchain.get_chain()}

    elif cmd == "TXN":                    # 新交易
        try:
            data = json.loads(payload) if payload else payload
        except json.JSONDecodeError:
            data = payload
        blockchain.add_data(data)
        reply = {"type": "ACK_TXN", "data": "queued"}

    elif cmd == "MINE":                   # 立即挖矿
        new_block = blockchain.mine_block()
        reply = {"type": "NEW_BLOCK", "data": new_block}
        # 广播 SYNC（可扩展成最长链比较逻辑）
        for pid in peer.get_peer_ids():
            if pid != peer.myid:
                peer.send_to_peer(pid, "BCRQ", "SYNC", waitreply=False)

    elif cmd == "SYNC":                   # 只返回链长
        reply = {"type": "LEN", "data": len(blockchain.get_chain())}

    else:
        reply = {"type": "ERROR", "data": f"Unknown BC command: {cmd}"}

    conn.senddata("BCRS", json.dumps(reply))


def bc_response_handler(peer, msgdata: str) -> None:
    """客户端打印解析，可在 CLI 回调中使用。"""
    try:
        obj = json.loads(msgdata)
    except json.JSONDecodeError:
        print("[BC] Malformed:", msgdata)
        return

    rtype, data = obj.get("type"), obj.get("data")
    if rtype == "CHAIN":
        print("=== Blockchain (len =", len(data), ") ===")
        for blk in data:
            print(f"# {blk['index']:>3}  txs={len(blk['data'])} proof={blk['proof']}")
    elif rtype == "NEW_BLOCK":
        print("+++ New block mined:", data)
    elif rtype == "ACK_TXN":
        print("→ TX accepted; will be mined soon")
    elif rtype == "LEN":
        print("Peer chain length:", data)
    elif rtype == "ERROR":
        print("[BC-ERROR]", data)
    else:
        print("[BC]", obj)