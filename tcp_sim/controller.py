# -*- coding: utf-8 -*-
"""拥塞控制算法层：CongestionController 抽象基类 + TCP Reno 实现。

文档要求（3.3.2 / 4.2.2）：
- 状态初始化：cwnd = 1 MSS、state = SLOW_START、time = 0
- 慢启动：每收到一个 ACK 执行 cwnd += 1 MSS，等效于每个 RTT 翻倍（指数增长）
- 拥塞避免：每收到一个 ACK 执行 cwnd += MSS²/cwnd，等效于每个 RTT 增加约 1 MSS（线性增长）
- 超时：ssthresh = max(cwnd/2, 2)、cwnd = 1，状态重置为慢启动
- 快速重传/恢复：3 个重复 ACK 时 ssthresh = max(cwnd/2, 2)、cwnd = ssthresh，
  进入快速恢复，避免 cwnd 直接归 1
- 可扩展性（3.4.3）：CongestionController 抽象为基类，未来可新增 CUBIC、BBR、Vegas 等子类
"""

from __future__ import annotations

from abc import ABC, abstractmethod

# 状态机状态
SLOW_START = "慢启动"
CONGESTION_AVOIDANCE = "拥塞避免"
FAST_RECOVERY = "快速恢复"

# 网络事件类型
NO_LOSS = "NO_LOSS"            # 正常收到 ACK
TIMEOUT = "TIMEOUT"            # 超时
TRIPLE_DUP_ACK = "3_DUP_ACK"   # 3 个重复 ACK（快速重传）


class CongestionController(ABC):
    """拥塞控制算法抽象基类。

    维护核心状态变量：cwnd、ssthresh、state。
    子类只需实现 on_ack / on_timeout / on_dup_ack 三个事件处理逻辑，
    即可平滑扩展新算法（CUBIC、BBR、Vegas 等），无需修改引擎与界面。
    """

    def __init__(self, ssthresh: float = 32.0) -> None:
        self.init_ssthresh: float = float(ssthresh)
        self.reset()

    def reset(self) -> None:
        """状态初始化：cwnd = 1 MSS、state = SLOW_START。"""
        self.cwnd: float = 1.0
        self.ssthresh: float = self.init_ssthresh
        self.state: str = SLOW_START

    @abstractmethod
    def on_ack(self) -> None:
        """收到一个新 ACK 时更新 cwnd 与状态。"""

    @abstractmethod
    def on_timeout(self) -> None:
        """发生超时时更新 ssthresh、cwnd 与状态。"""

    @abstractmethod
    def on_dup_ack(self) -> None:
        """收到 3 个重复 ACK（快速重传/快速恢复）时更新状态。"""


class RenoController(CongestionController):
    """TCP Reno 拥塞控制算法。

    仿真按 RTT 离散推进，因此将"每 ACK 更新"折算为"每 RTT 更新"：
    - 慢启动：cwnd *= 2（等效于每 ACK cwnd += 1 MSS）
    - 拥塞避免：cwnd += 1（等效于每 ACK cwnd += MSS²/cwnd，每 RTT 约 +1 MSS）
    """

    def on_ack(self) -> None:
        if self.state == SLOW_START:
            # 指数增长；到达阈值时切换到拥塞避免
            self.cwnd *= 2.0
            if self.cwnd >= self.ssthresh:
                self.cwnd = float(self.ssthresh)
                self.state = CONGESTION_AVOIDANCE
        elif self.state == CONGESTION_AVOIDANCE:
            # 线性增长，每个 RTT +1 MSS
            self.cwnd += 1.0
        elif self.state == FAST_RECOVERY:
            # 快速恢复阶段按拥塞避免方式增长，一个 RTT 后退出恢复
            self.cwnd += 1.0
            self.state = CONGESTION_AVOIDANCE

    def on_timeout(self) -> None:
        # 文档 3.3.2：ssthresh = max(cwnd/2, 2)、cwnd = 1、回到慢启动
        self.ssthresh = max(self.cwnd / 2.0, 2.0)
        self.cwnd = 1.0
        self.state = SLOW_START

    def on_dup_ack(self) -> None:
        # 文档 3.3.2：ssthresh = max(cwnd/2, 2)、cwnd = ssthresh、进入快速恢复
        self.ssthresh = max(self.cwnd / 2.0, 2.0)
        self.cwnd = float(self.ssthresh)
        self.state = FAST_RECOVERY
