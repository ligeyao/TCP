# -*- coding: utf-8 -*-
"""仿真引擎：状态机调度，按 RTT 推进时间轴，驱动整个仿真循环。

文档要求（3.3.2 (7)）：
- 由 SimulationEngine 协调控制器与网络模拟器，按 RTT 推进时间轴，
  驱动整个仿真循环运行。
- 网络模拟器按丢包率判定本轮事件，控制器根据事件类型执行
  慢启动、拥塞避免、超时或快速重传处理，每轮结束后记录数据并刷新曲线。

设计说明：
- step() 只推进一轮，界面层用 root.after() 定时器循环调用 step()，
  实现"定时器调度"（文档 2.2.1 主要技术）。
- 连续运行时界面可一次批量执行多轮（run_batch），保证 1000 轮在
  3 秒内完成（文档 3.4.1 性能需求），同时按刷新率重绘曲线。
"""

from __future__ import annotations

from .config import SimulationConfig
from .controller import RenoController, CongestionController, NO_LOSS, TIMEOUT, TRIPLE_DUP_ACK
from .network import NetworkSimulator
from .recorder import DataRecorder


class SimulationEngine:
    """仿真引擎：协调控制器、网络模拟器与数据记录器。

    职责：
    - 初始化仿真状态（cwnd=1 MSS、SLOW_START、time=0）
    - 按 RTT 推进：网络模拟器判定事件 → 控制器处理事件 → 记录数据
    - 对外提供 step() / run_batch() / reset() / is_finished 等控制接口
    """

    def __init__(self, config: SimulationConfig, seed: int | None = None) -> None:
        self.config = config
        self.seed = seed
        self.controller: CongestionController = RenoController(ssthresh=config.ssthresh)
        self.network = NetworkSimulator(loss_rate=config.loss_rate, seed=seed)
        self.recorder = DataRecorder()
        self.time = 0          # 当前轮次（每轮 = 一个 RTT）
        self.finished = False

    # ------------------------------------------------------------------
    # 状态管理
    # ------------------------------------------------------------------
    def reset(self, seed: int | None = None) -> None:
        """重置仿真：清空历史、恢复初始状态。"""
        self.controller.reset()
        self.network.reset(seed if seed is not None else self.seed)
        self.recorder.reset()
        self.time = 0
        self.finished = False

    def is_finished(self) -> bool:
        return self.finished or self.time >= self.config.rounds

    # ------------------------------------------------------------------
    # 仿真推进
    # ------------------------------------------------------------------
    def step(self) -> bool:
        """推进一轮仿真（一个 RTT）。

        返回 True 表示本轮正常执行；返回 False 表示仿真已结束。
        """
        if self.is_finished():
            self.finished = True
            return False

        # 1. 记录本轮开始前的状态（time 从 0 开始，与文档一致）
        self.recorder.record_round(
            time=self.time,
            cwnd=self.controller.cwnd,
            ssthresh=self.controller.ssthresh,
            state=self.controller.state,
        )

        # 2. 网络模拟器判定本轮事件（文档 3.3.2 (6)）
        event = self.network.simulate_round(self.controller.cwnd)

        # 3. 控制器处理事件（文档 3.3.2）
        if event == TIMEOUT:
            self.controller.on_timeout()
            self.recorder.record_event(self.time + 1, self.time + 1, TIMEOUT)
        elif event == TRIPLE_DUP_ACK:
            self.controller.on_dup_ack()
            self.recorder.record_event(self.time + 1, self.time + 1, TRIPLE_DUP_ACK)
        else:  # NO_LOSS
            self.controller.on_ack()

        # 4. 时间轴推进一个 RTT
        self.time += 1

        if self.time >= self.config.rounds:
            self.finished = True
        return True

    def run_batch(self, max_rounds: int | None = None, max_time_ms: float = 40.0) -> int:
        """连续执行多轮（供界面定时器批量调用）。

        - max_rounds：单批最多执行的轮数（None 表示不限制）
        - max_time_ms：单批最大耗时（毫秒），保证界面刷新不低于 10 FPS
        返回本批实际执行的轮数。
        """
        import time as _time

        start = _time.perf_counter()
        executed = 0
        while not self.is_finished():
            if max_rounds is not None and executed >= max_rounds:
                break
            self.step()
            executed += 1
            if (_time.perf_counter() - start) * 1000.0 >= max_time_ms:
                break
        return executed

    # ------------------------------------------------------------------
    # 结果
    # ------------------------------------------------------------------
    def compute_stats(self) -> dict:
        """计算本次仿真的性能指标（转发给记录器）。"""
        return self.recorder.compute_stats(self.config.mss, self.config.rtt)
