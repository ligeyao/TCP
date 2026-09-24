# -*- coding: utf-8 -*-
"""网络模拟器：随机丢包模拟。

文档要求（3.3.2 / 4.2.2）：
- 根据用户设置的丢包率，每轮用伪随机数判定本轮是否丢包：
  若 random() < loss_rate，则触发超时事件；否则正常返回 ACK。
- 同时模拟三重重复 ACK（快速重传）事件：当 cwnd 足够大（>= 4 MSS）时，
  部分丢包以"3 个重复 ACK"的形式表现，从而触发快速恢复。

事件类型：
- NO_LOSS       正常返回 ACK
- TIMEOUT       超时（丢包后重传定时器超时）
- TRIPLE_DUP_ACK 3 个重复 ACK（快速重传）
"""

from __future__ import annotations

import random

from .controller import NO_LOSS, TIMEOUT, TRIPLE_DUP_ACK


class NetworkSimulator:
    """网络模拟器：以伪随机数模拟真实网络中的丢包事件。

    - loss_rate：用户设定的丢包率（0 ~ 1）
    - dup_ack_ratio：丢包事件中表现为三重重复 ACK 的比例（其余表现为超时）
    - seed：随机种子（可选），设置后实验可复现
    """

    def __init__(self, loss_rate: float = 0.02, dup_ack_ratio: float = 0.3, seed: int | None = None) -> None:
        self.loss_rate = float(loss_rate)
        self.dup_ack_ratio = float(dup_ack_ratio)
        self.rng = random.Random(seed)

    def reset(self, seed: int | None = None) -> None:
        """重置随机数发生器。"""
        self.rng = random.Random(seed)

    def simulate_round(self, cwnd: float) -> str:
        """判定本轮网络事件。

        规则：
        1. random() < loss_rate  → 发生丢包
           - cwnd >= 4 且 random() < dup_ack_ratio → 三重重复 ACK（快速重传）
           - 否则 → 超时
        2. 否则正常返回 ACK

        cwnd < 4 时在途报文不足，无法凑齐 3 个重复 ACK，因此只触发超时。
        """
        if self.rng.random() < self.loss_rate:
            if cwnd >= 4.0 and self.rng.random() < self.dup_ack_ratio:
                return TRIPLE_DUP_ACK
            return TIMEOUT
        return NO_LOSS
