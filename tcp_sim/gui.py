# -*- coding: utf-8 -*-
"""视图层：Tkinter 图形用户界面。

文档要求（3.3 / 4.2.1 前台管理模块）：
- 参数配置区：ssthresh、RTT、MSS、丢包率、仿真轮数
- 控制按钮：开始、暂停、重置、单步
- 实时 cwnd 曲线区（Matplotlib 嵌入）
- 状态显示区：当前 cwnd、ssthresh、所处阶段、仿真进度
- 数据统计与导出：CSV 导出、曲线 PNG 保存
- 性能需求（3.4.1）：采用 root.after() 定时器控制刷新频率，界面响应 < 200ms

界面布局：
┌──────────────┬──────────────────────────────┬──────────────┐
│ 参数配置区    │      实时曲线区（Matplotlib）   │ 状态显示区    │
│ 控制按钮区    │                              │ 性能指标区    │
│              │                              │ 关键事件区    │
└──────────────┴──────────────────────────────┴──────────────┘
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from .config import SimulationConfig, DEFAULT_PARAMS, CONFIG_FILE, CSV_DIR, IMAGES_DIR, ensure_dirs
from .database import SimulationDB
from .engine import SimulationEngine
from .plotter import CwndPlotter

# 界面刷新周期（ms）：20 FPS，满足文档"曲线刷新率不低于 10 FPS"
REFRESH_MS = 50

# 参数输入项定义：(键名, 显示标签, 说明)
PARAM_FIELDS = [
    ("ssthresh", "慢启动阈值 ssthresh (MSS)", "例如 32"),
    ("rtt", "RTT 时延 (ms)", "例如 100"),
    ("mss", "MSS 大小 (字节)", "例如 1460"),
    ("loss_rate", "随机丢包率 (0~1)", "例如 0.02"),
    ("rounds", "仿真轮数", "例如 100"),
]


class MainApp:
    """TCP 拥塞控制仿真系统主界面。"""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("TCP 拥塞控制算法仿真系统（Reno）")
        self.root.geometry("1200x720")
        self.root.minsize(1000, 620)

        # 确保四个专用目录存在（config / csv / images / data）
        ensure_dirs()

        # 配置：启动时自动加载 config/config.json（文档 3.3.1 (7)）
        self.config = SimulationConfig.load_json(CONFIG_FILE)

        # 引擎、绘图器、数据库与定时器
        self.engine: SimulationEngine | None = None
        self.plotter = CwndPlotter()
        self.db = SimulationDB()          # SQLite 自动存储（文档 2.1 / 4.2.2）
        self._last_saved_sim_id: int | None = None
        self._after_id: str | None = None
        self._running = False

        self._build_ui()
        self._fill_entries_from_config()
        self._refresh_status(reset=True)

        # 关闭窗口时自动保存配置
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ==================================================================
    # 界面构建
    # ==================================================================
    def _build_ui(self) -> None:
        # ---------- 左侧：参数 + 控制 ----------
        left = ttk.Frame(self.root, padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y)

        param_box = ttk.LabelFrame(left, text="参数配置（参数合法性校验）", padding=6)
        param_box.pack(fill=tk.X)

        self.param_vars: dict[str, tk.StringVar] = {}
        for i, (key, label, hint) in enumerate(PARAM_FIELDS):
            ttk.Label(param_box, text=label).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.StringVar()
            entry = ttk.Entry(param_box, textvariable=var, width=14, justify="right")
            entry.grid(row=i, column=1, sticky="e", pady=3, padx=(6, 0))
            ttk.Label(param_box, text=hint, foreground="#888888").grid(
                row=i, column=2, sticky="w", padx=(4, 0))
            self.param_vars[key] = var

        ctrl_box = ttk.LabelFrame(left, text="仿真控制", padding=6)
        ctrl_box.pack(fill=tk.X, pady=(8, 0))

        self.btn_start = ttk.Button(ctrl_box, text="开始", command=self._on_start)
        self.btn_pause = ttk.Button(ctrl_box, text="暂停", command=self._on_pause)
        self.btn_step = ttk.Button(ctrl_box, text="单步", command=self._on_step)
        self.btn_reset = ttk.Button(ctrl_box, text="重置", command=self._on_reset)

        self.btn_start.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        self.btn_pause.grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        self.btn_step.grid(row=1, column=0, sticky="ew", padx=2, pady=2)
        self.btn_reset.grid(row=1, column=1, sticky="ew", padx=2, pady=2)
        ctrl_box.columnconfigure(0, weight=1)
        ctrl_box.columnconfigure(1, weight=1)

        # 进度条
        ttk.Label(ctrl_box, text="仿真进度").grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.progress = ttk.Progressbar(ctrl_box, maximum=100)
        self.progress.grid(row=3, column=0, columnspan=2, sticky="ew", pady=2)
        ctrl_box.columnconfigure(0, weight=1)
        ctrl_box.columnconfigure(1, weight=1)

        tool_box = ttk.LabelFrame(left, text="配置与导出", padding=6)
        tool_box.pack(fill=tk.X, pady=(8, 0))

        ttk.Button(tool_box, text="恢复默认参数", command=self._on_default_params).pack(fill=tk.X, pady=2)
        ttk.Button(tool_box, text="保存配置(JSON)", command=self._on_save_config).pack(fill=tk.X, pady=2)
        ttk.Button(tool_box, text="导出数据(CSV)", command=self._on_export_csv).pack(fill=tk.X, pady=2)
        ttk.Button(tool_box, text="保存曲线(PNG)", command=self._on_save_png).pack(fill=tk.X, pady=2)

        # ---------- 中间：曲线区 ----------
        center = ttk.Frame(self.root, padding=6)
        center.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = FigureCanvasTkAgg(self.plotter.figure, master=center)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # ---------- 右侧：状态 / 统计 / 事件 ----------
        right = ttk.Frame(self.root, padding=8)
        right.pack(side=tk.RIGHT, fill=tk.Y)

        status_box = ttk.LabelFrame(right, text="当前状态", padding=6)
        status_box.pack(fill=tk.X)

        self.lbl_cwnd = ttk.Label(status_box, text="cwnd：-- MSS")
        self.lbl_ssthresh = ttk.Label(status_box, text="ssthresh：-- MSS")
        self.lbl_state = ttk.Label(status_box, text="所处阶段：--")
        self.lbl_time = ttk.Label(status_box, text="仿真轮次：0 / 0")
        for lbl in (self.lbl_cwnd, self.lbl_ssthresh, self.lbl_state, self.lbl_time):
            lbl.pack(anchor="w", pady=1)

        stats_box = ttk.LabelFrame(right, text="性能指标（仿真结束后显示）", padding=6)
        stats_box.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.stats_text = tk.Text(stats_box, width=34, height=12, font=("Consolas", 9),
                                  state="disabled", relief="flat", bg="#f5f5f5")
        self.stats_text.pack(fill=tk.BOTH, expand=True)

        event_box = ttk.LabelFrame(right, text="关键事件（超时 / 快速重传）", padding=6)
        event_box.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        self.event_text = tk.Text(event_box, width=34, height=8, font=("Consolas", 9),
                                  state="disabled", relief="flat", bg="#f5f5f5")
        self.event_text.pack(fill=tk.BOTH, expand=True)

    # ==================================================================
    # 参数配置
    # ==================================================================
    def _fill_entries_from_config(self) -> None:
        for key, _label, _hint in PARAM_FIELDS:
            self.param_vars[key].set(str(getattr(self.config, key)))

    def _get_config_from_entries(self) -> SimulationConfig:
        return SimulationConfig.from_strings(
            ssthresh=self.param_vars["ssthresh"].get(),
            rtt=self.param_vars["rtt"].get(),
            mss=self.param_vars["mss"].get(),
            loss_rate=self.param_vars["loss_rate"].get(),
            rounds=self.param_vars["rounds"].get(),
        )

    def _validate_and_get_config(self) -> SimulationConfig | None:
        """校验参数；非法则弹出提示并阻止启动（文档 3.3.1 (6)）。"""
        config = self._get_config_from_entries()
        errors = config.validate()
        if errors:
            messagebox.showerror("参数校验失败", "请检查以下参数：\n\n" + "\n".join(f"• {e}" for e in errors))
            return None
        self.config = config
        return config

    def _on_default_params(self) -> None:
        for key in DEFAULT_PARAMS:
            self.param_vars[key].set(str(DEFAULT_PARAMS[key]))

    def _on_save_config(self) -> None:
        config = self._get_config_from_entries()
        errors = config.validate()
        if errors:
            messagebox.showerror("参数校验失败", "\n".join(f"• {e}" for e in errors))
            return
        self.config = config
        try:
            self.config.save_json(CONFIG_FILE)
            messagebox.showinfo("保存成功", f"配置已保存到：\n{CONFIG_FILE}")
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc))

    # ==================================================================
    # 仿真控制
    # ==================================================================
    def _ensure_engine(self) -> SimulationEngine | None:
        """当前没有引擎或引擎已结束时，按当前参数创建新引擎。"""
        if self.engine is None or self.engine.is_finished():
            config = self._validate_and_get_config()
            if config is None:
                return None
            self.engine = SimulationEngine(config)
            self._reset_ui_state()
        return self.engine

    def _reset_ui_state(self) -> None:
        """清空曲线、事件与统计显示。"""
        self.plotter.clear()
        self._set_text(self.stats_text, "")
        self._set_text(self.event_text, "")
        self.progress.configure(value=0, maximum=100)
        self._last_saved_sim_id = None

    def _on_start(self) -> None:
        if self._running:
            return
        config = self._validate_and_get_config()
        if config is None:
            return
        self.engine = SimulationEngine(config)
        self._reset_ui_state()
        self.progress.configure(maximum=max(1, config.rounds))
        self._running = True
        self._schedule_next()

    def _on_pause(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None

    def _on_step(self) -> None:
        """单步执行：逐轮推进，便于细致观察 cwnd 演化（文档 4.2.1 (3)）。"""
        if self._running:
            self._on_pause()
        engine = self._ensure_engine()
        if engine is None:
            return
        self.progress.configure(maximum=max(1, engine.config.rounds))
        engine.step()
        self._refresh_ui()

    def _on_reset(self) -> None:
        """重置：停止仿真并清空数据（文档 4.2.1 (3)）。"""
        self._on_pause()
        if self.engine is not None:
            self.engine.reset()
        else:
            self.engine = None
        self._reset_ui_state()
        self._refresh_status(reset=True)

    def _schedule_next(self) -> None:
        if self._running:
            self._after_id = self.root.after(REFRESH_MS, self._tick)

    def _tick(self) -> None:
        """定时器回调：批量推进仿真并刷新界面（文档 3.4.1 用 root.after 控制刷新频率）。"""
        if not self._running or self.engine is None:
            return

        # 单批最多执行 40ms，保证界面刷新率约 20 FPS 且响应流畅
        self.engine.run_batch(max_time_ms=40.0)
        self._refresh_ui()

        if self.engine.is_finished():
            self._running = False
            self._after_id = None
            return
        self._schedule_next()

    # ==================================================================
    # 界面刷新
    # ==================================================================
    def _refresh_ui(self) -> None:
        if self.engine is None:
            return
        self.plotter.update(self.engine.recorder.records, self.engine.recorder.events)
        self._refresh_status()
        self._refresh_events()
        if self.engine.is_finished():
            self._refresh_stats()
            self._auto_save_to_db()

    def _auto_save_to_db(self) -> None:
        """仿真结束后自动保存到 SQLite（文档 2.1 / 4.2.2 数据记录管理）。

        每次仿真只保存一次；保存成功后在统计区底部追加提示。
        """
        if self.engine is None or self._last_saved_sim_id is not None:
            return
        try:
            stats = self.engine.compute_stats()
            sim_id = self.db.save_simulation(
                config=self.engine.config,
                stats=stats,
                records=self.engine.recorder.records,
                events=self.engine.recorder.events,
            )
            self._last_saved_sim_id = sim_id
            tip = f"\n\n已自动保存到 SQLite 数据库（记录 ID #{sim_id}）\n文件位置：data/simulation.db"
        except Exception as exc:  # 数据库异常不打断用户，只做提示
            tip = f"\n\nSQLite 自动保存失败：{exc}"

        self.stats_text.configure(state="normal")
        self.stats_text.insert(tk.END, tip)
        self.stats_text.configure(state="disabled")

    def _refresh_status(self, reset: bool = False) -> None:
        if reset or self.engine is None:
            self.lbl_cwnd.configure(text="cwnd：-- MSS")
            self.lbl_ssthresh.configure(text="ssthresh：-- MSS")
            self.lbl_state.configure(text="所处阶段：--")
            self.lbl_time.configure(text="仿真轮次：0 / 0")
            self.progress.configure(value=0)
            return

        c = self.engine.controller
        total = max(1, self.engine.config.rounds)
        self.lbl_cwnd.configure(text=f"cwnd：{c.cwnd:.3f} MSS")
        self.lbl_ssthresh.configure(text=f"ssthresh：{c.ssthresh:.3f} MSS")
        self.lbl_state.configure(text=f"所处阶段：{c.state}")
        self.lbl_time.configure(text=f"仿真轮次：{self.engine.time} / {total}")
        self.progress.configure(value=self.engine.time)
        if self.engine.is_finished():
            self.lbl_time.configure(text=f"仿真轮次：{total} / {total}（已完成）")

    def _refresh_events(self) -> None:
        if self.engine is None:
            return
        events = self.engine.recorder.events
        lines = [f"第 {ev['round']} 轮  |  {ev['type']}" for ev in events[-200:]]
        self._set_text(self.event_text, "\n".join(lines))

    def _refresh_stats(self) -> None:
        if self.engine is None:
            return
        stats = self.engine.compute_stats()
        lines = [f"{key}：{value}" for key, value in stats.items()]
        self._set_text(self.stats_text, "\n".join(lines))

    @staticmethod
    def _set_text(widget: tk.Text, content: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert("1.0", content)
        widget.configure(state="disabled")

    # ==================================================================
    # 导出（文档 3.3.3 (4)(5)(6)）
    # ==================================================================
    def _on_export_csv(self) -> None:
        if self.engine is None or not self.engine.recorder.records:
            messagebox.showwarning("提示", "暂无仿真数据，请先运行仿真")
            return
        path = filedialog.asksaveasfilename(
            title="导出仿真数据",
            defaultextension=".csv",
            filetypes=[("CSV 文件", "*.csv")],
            initialdir=CSV_DIR,
            initialfile="tcp_sim_records.csv",
        )
        if not path:
            return
        try:
            self.engine.recorder.export_csv(path)
            messagebox.showinfo("导出成功", f"数据已导出到：\n{path}")
        except (OSError, ValueError) as exc:
            messagebox.showerror("导出失败", str(exc))

    def _on_save_png(self) -> None:
        if self.engine is None or not self.engine.recorder.records:
            messagebox.showwarning("提示", "暂无仿真曲线，请先运行仿真")
            return
        path = filedialog.asksaveasfilename(
            title="保存 cwnd 曲线",
            defaultextension=".png",
            filetypes=[("PNG 图片", "*.png")],
            initialdir=IMAGES_DIR,
            initialfile="tcp_cwnd_curve.png",
        )
        if not path:
            return
        try:
            self.plotter.save_png(path, dpi=150)  # 分辨率可调（文档 3.3.3 (5)）
            messagebox.showinfo("保存成功", f"曲线已保存到：\n{path}")
        except OSError as exc:
            messagebox.showerror("保存失败", str(exc))

    # ==================================================================
    # 退出
    # ==================================================================
    def _on_close(self) -> None:
        self._on_pause()
        try:
            config = self._get_config_from_entries()
            if not config.validate():
                config.save_json(CONFIG_FILE)
        except (OSError, ValueError):
            pass
        self.db.close()
        self.root.destroy()


def run() -> None:
    """启动 GUI 主循环。"""
    root = tk.Tk()
    MainApp(root)
    root.mainloop()
