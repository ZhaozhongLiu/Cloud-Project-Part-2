#!/usr/bin/env python3
# bc_api.py
"""
统一 Blockchain 访问层
~~~~~~~~~~~~~~~~~~~~~
• 如果本机就是 BC 节点 → 直接操作内存中的 `blockchain` 实例
• 否则 → 自动找到已知的远程 BC 节点，通过 P2P 发送 BCRQ 并等待回应

公开函数
--------
add_data(peer, data)      – 把 data 放入 pending 池
mine_block(peer)          – 打包 pending 数据并挖新区块，返回区块 dict
get_chain(peer)           – 获得完整链 list[block]
query(peer, key, value)   – 简易筛选（可选）
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List

from bc_handlers import blockchain   # 本地实例（若 peertype == BC）


# ------------------------------------------------------------------ #
# 内部工具
# ------------------------------------------------------------------ #
def _find_bc_peer(peer) -> str | None:
    """返回第一个已知 BC peer 的 peerid；若无返回 None。"""
    for pid, (_, _, ptype) in peer.peers.items():
        if ptype == "BC":
            return pid
    return None


def _rpc(peer, cmd: str, payload: str | None = None):
    """向远程 BC 节点发送 BCRQ 并返回反序列化后的 JSON 对象。"""
    target = _find_bc_peer(peer)
    if not target:
        raise RuntimeError("No known BC peer")

    msg = cmd.upper() if payload is None else f"{cmd.upper()} {payload}"
    replies = peer.send_to_peer(target, "BCRQ", msg, waitreply=True)
    if not replies:
        raise RuntimeError("No reply from BC peer")

    mtype, mdata = replies[0]
    if mtype != "BCRS":
        raise RuntimeError(f"Unexpected reply type: {mtype}")

    obj = json.loads(mdata)
    if obj.get("type") == "ERROR":
        raise RuntimeError(obj["data"])
    return obj


# ------------------------------------------------------------------ #
# 公共 API
# ------------------------------------------------------------------ #
def add_data(peer, data: Any) -> None:
    """写数据（本地或远程）。"""
    if getattr(peer, "peertype", "").upper() == "BC":
        blockchain.add_data(data)
    else:
        _rpc(peer, "TXN", json.dumps(data))


def mine_block(peer) -> Dict[str, Any]:
    """挖矿（本地或远程），返回新区块 dict。"""
    if getattr(peer, "peertype", "").upper() == "BC":
        return blockchain.mine_block()
    return _rpc(peer, "MINE")["data"]


def get_chain(peer) -> List[Dict[str, Any]]:
    """获取完整链 list[block]。"""
    if getattr(peer, "peertype", "").upper() == "BC":
        return blockchain.get_chain()
    return _rpc(peer, "GET")["data"]


# 可选：按键值过滤区块
def query(
        peer,
        key: str,
        value: Any,
        predicate: Callable[[Any], bool] | None = None,
) -> List[Dict[str, Any]]:
    """
    返回所有含指定 (key, value) 的区块；或使用自定义 predicate(tx)。
    """
    if predicate is None:
        predicate = lambda tx: isinstance(tx, dict) and tx.get(key) == value  # type: ignore[arg-type]

    chain = get_chain(peer)
    return [blk for blk in chain if any(predicate(tx) for tx in blk["data"])]