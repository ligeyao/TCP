# -*- coding: utf-8 -*-
"""数据记录器：逐轮记录、关键事件记录、性能指标计算与 CSV 导出。

文档要求（3.3.3）：
- 数据采集与记录：每推进一轮采集 time、cwnd、ssthresh、state 四个字段
- 关键事件记录：记录每次超时与快速重传的发生时间与轮次
- 性能指标计算：平均吞吐量（平均 cwnd × MSS / RTT）、拥塞发生次数
  （超时次数 + 快速重传次数）、慢启动到拥塞避免的切换轮数、cwnd 峰值与谷值
- CSV 数据导出：字段与仿真记录一一对应，可用 Excel 二次分析
- 导出异常处理：校验路径合法性、捕获读写失败
"""

from __future__ import annotations

import csv
import os

from .controller import SLOW_START, CONGESTION_AVOIDANCE, FAST_RECOVERY, TIMEOUT, TRIPLE_DUP_ACK


class DataRecorder:
    """仿真数据记录器（内存列表 + CSV 导出）。"""

    def __init__(self) -> None:
        self.records: list[dict] = []       # 每轮记录：time, cwnd, ssthresh, state
        self.events: list[dict] = []        # 关键事件：round, time, type
        self.timeout_count = 0
        self.dup_ack_count = 0

    def reset(self) -> None:
        """清空历史记录。"""
        self.records.clear()
        self.events.clear()
        self.timeout_count = 0
        self.dup_ack_count = 0

    # ------------------------------------------------------------------
    # 数据采集
    # ------------------------------------------------------------------
    def record_round(self, time: int, cwnd: float, ssthresh: float, state: str) -> None:
        """追加一轮仿真记录（文档 3.3.3 (1)：数据与仿真过程严格同步）。"""
        self.records.append({
            "time": time,
            "cwnd": round(cwnd, 3),
            "ssthresh": round(ssthresh, 3),
            "state": state,
        })

    def record_event(self, round_no: int, time: int, event_type: str) -> None:
        """记录一次关键事件（超时 / 快速重传）。"""
        label = "超时" if event_type == TIMEOUT else "快速重传"
        self.events.append({"round": round_no, "time": time, "type": label})
        if event_type == TIMEOUT:
            self.timeout_count += 1
        elif event_type == TRIPLE_DUP_ACK:
            self.dup_ack_count += 1

    # ------------------------------------------------------------------
    # 性能指标计算（文档 3.3.3 (3)）
    # ------------------------------------------------------------------
    def compute_stats(self, mss: float, rtt: float) -> dict:
        """仿真结束后计算性能指标。"""
        if not self.records:
            return {
                "平均吞吐量(Mbps)": 0.0,
                "拥塞发生次数": 0,
                "超时次数": 0,
                "快速重传次数": 0,
                "切换到拥塞避免的轮数": None,
                "cwnd 峰值(MSS)": 0.0,
                "cwnd 谷值(MSS)": 0.0,
                "最终 cwnd(MSS)": 0.0,
            }

        cwnd_list = [r["cwnd"] for r in self.records]
        avg_cwnd = sum(cwnd_list) / len(cwnd_list)

        # 平均吞吐量 = 平均 cwnd × MSS / RTT（转换为 Mbps）
        # cwnd 单位为 MSS 个数，MSS 单位为字节，RTT 单位为 ms
        throughput_bytes_per_ms = avg_cwnd * mss / rtt          # 字节/ms
        throughput_mbps = throughput_bytes_per_ms * 8 / 1000    # (字节/ms)*8 → bit/ms → /1000 → Mbps

        # 慢启动 → 拥塞避免 的切换轮数（首个进入拥塞避免/快速恢复的轮次）
        switch_round = None
        for r in self.records:
            if r["state"] in (CONGESTION_AVOIDANCE, FAST_RECOVERY):
                switch_round = r["time"]
                break

        return {
            "平均吞吐量(Mbps)": round(throughput_mbps, 4),
            "拥塞发生次数": self.timeout_count + self.dup_ack_count,
            "超时次数": self.timeout_count,
            "快速重传次数": self.dup_ack_count,
            "切换到拥塞避免的轮数": switch_round,
            "cwnd 峰值(MSS)": max(cwnd_list),
            "cwnd 谷值(MSS)": min(cwnd_list),
            "最终 cwnd(MSS)": cwnd_list[-1],
        }

    # ------------------------------------------------------------------
    # CSV 导出（文档 3.3.3 (4) / (6)：导出异常处理）
    # ------------------------------------------------------------------
    def export_csv(self, path: str) -> None:
        """将全部记录导出为 CSV 文件。

        失败时抛出带中文提示的异常，由界面层捕获并提示用户。
        """
        if not self.records:
            raise ValueError("暂无仿真数据，请先运行仿真")

        # 路径合法性校验：目录必须存在且可写
        directory = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(directory):
            raise OSError(f"保存目录不存在：{directory}")

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.DictWriter(f, fieldnames=["time", "cwnd", "ssthresh", "state"])
                writer.writeheader()
                writer.writerows(self.records)
        except OSError as exc:
            raise OSError(f"CSV 写入失败：{exc}") from exc
