# -*- coding: utf-8 -*-
"""绘图层：Matplotlib 动态绘图（cwnd 曲线 + ssthresh 阈值线 + 阶段底色 + 事件标注）。

文档要求：
- 4.2.1 (2)：曲线图展示包括 ssthresh 阈值线、阶段底色区分、关键事件标注等
- 3.3.3 (5)：cwnd 曲线可保存为 PNG 图片（分辨率可调）
- 3.4.1 性能需求：曲线刷新率不低于 10 FPS；支持 10000 轮以上数据记录与绘图
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("TkAgg")  # 嵌入 Tkinter 使用 TkAgg 后端
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
matplotlib.rcParams["axes.unicode_minus"] = False  # 正常显示负号
from matplotlib.figure import Figure

from .controller import SLOW_START, CONGESTION_AVOIDANCE, FAST_RECOVERY

# 阶段底色（alpha 低，不干扰曲线）
PHASE_COLORS = {
    SLOW_START: "#2ecc71",          # 绿色
    CONGESTION_AVOIDANCE: "#3498db",  # 蓝色
    FAST_RECOVERY: "#f39c12",       # 橙色
}

EVENT_STYLE = {
    "超时": {"marker": "x", "color": "red", "s": 90, "label": "超时"},
    "快速重传": {"marker": "v", "color": "purple", "s": 90, "label": "快速重传"},
}


class CwndPlotter:
    """cwnd 动态曲线绘图器。

    职责：维护 Figure/Axes，根据记录数据绘制曲线、阈值线、阶段底色与
    事件标注，并支持将曲线保存为 PNG（分辨率可调）。
    """

    def __init__(self) -> None:
        self.figure = Figure(figsize=(7.0, 4.5), dpi=100, facecolor="white")
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("TCP Reno 拥塞窗口 cwnd 动态曲线")
        self.ax.set_xlabel("仿真轮次 (RTT)")
        self.ax.set_ylabel("cwnd (MSS)")
        self.ax.grid(True, linestyle="--", alpha=0.4)
        self._event_legend_added = set()

    # ------------------------------------------------------------------
    def clear(self) -> None:
        """清空绘图区。"""
        self.ax.clear()
        self._event_legend_added.clear()
        self._setup_axes()

    def _setup_axes(self) -> None:
        self.ax.set_title("TCP Reno 拥塞窗口 cwnd 动态曲线")
        self.ax.set_xlabel("仿真轮次 (RTT)")
        self.ax.set_ylabel("cwnd (MSS)")
        self.ax.grid(True, linestyle="--", alpha=0.4)

    # ------------------------------------------------------------------
    def update(self, records: list[dict], events: list[dict]) -> None:
        """根据记录数据重绘曲线。

        records：DataRecorder.records（time/cwnd/ssthresh/state）
        events ：DataRecorder.events（round/time/type）
        """
        self.ax.clear()
        self._setup_axes()
        if not records:
            if self.figure.canvas is not None:
                self.figure.canvas.draw_idle()
            return

        times = [r["time"] for r in records]
        cwnds = [r["cwnd"] for r in records]
        ssthreshes = [r["ssthresh"] for r in records]

        # ---- 阶段底色（按连续相同状态分段绘制 axvspan）----
        span_start = times[0]
        prev_state = records[0]["state"]
        for r in records[1:]:
            if r["state"] != prev_state:
                self._draw_phase_span(span_start, r["time"], prev_state)
                span_start = r["time"]
                prev_state = r["state"]
        self._draw_phase_span(span_start, times[-1] + 1, prev_state)

        # ---- cwnd 曲线与 ssthresh 阈值线 ----
        # 数据量很大时轻度抽稀显示，保证刷新流畅（文档 3.4.1）
        step = 1
        if len(times) > 4000:
            step = len(times) // 4000 + 1
        self.ax.plot(times[::step], cwnds[::step], color="#e74c3c", linewidth=1.8, label="cwnd")
        self.ax.plot(times[::step], ssthreshes[::step], color="#2c3e50",
                     linestyle="--", linewidth=1.2, label="ssthresh")

        # ---- 关键事件标注（超时 / 快速重传）----
        for ev in events:
            style = EVENT_STYLE.get(ev["type"])
            if style is None:
                continue
            self.ax.scatter([ev["time"] - 1], [self._cwnd_at(records, ev["time"] - 1)],
                            marker=style["marker"], color=style["color"], s=style["s"],
                            label=style["label"] if style["label"] not in self._event_legend_added else None,
                            zorder=5)
            self._event_legend_added.add(style["label"])

        # ---- 图例与自适应范围 ----
        self.ax.legend(loc="upper left", fontsize=8)
        self.ax.set_xlim(left=0)
        self.ax.set_ylim(bottom=0)

        if self.figure.canvas is not None:
            self.figure.canvas.draw_idle()

    @staticmethod
    def _cwnd_at(records: list[dict], time: int) -> float:
        """返回指定轮次的 cwnd 值（越界取最近值）。"""
        for r in reversed(records):
            if r["time"] <= time:
                return r["cwnd"]
        return 0.0

    def _draw_phase_span(self, x_start: float, x_end: float, state: str) -> None:
        color = PHASE_COLORS.get(state, "#cccccc")
        self.ax.axvspan(x_start, x_end, color=color, alpha=0.10)

    # ------------------------------------------------------------------
    # PNG 保存（文档 3.3.3 (5)：分辨率可调）
    # ------------------------------------------------------------------
    def save_png(self, path: str, dpi: int = 150) -> None:
        """将当前曲线保存为 PNG 图片，dpi 控制分辨率。"""
        directory = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(directory):
            raise OSError(f"保存目录不存在：{directory}")
        try:
            self.figure.savefig(path, dpi=dpi, bbox_inches="tight", facecolor="white")
        except OSError as exc:
            raise OSError(f"图片保存失败：{exc}") from exc
