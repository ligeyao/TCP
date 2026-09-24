# -*- coding: utf-8 -*-
"""SQLite 数据存储模块：仿真数据自动持久化。

文档要求：
- 2.1 开发环境：数据库使用 SQLite
- 4.2.2 后台管理模块：数据记录管理（记录每轮仿真数据并统计性能指标，
  为论文与实验报告提供数据支撑）

设计：
- 使用 Python 标准库 sqlite3，零额外依赖
- 数据库文件：data/simulation.db
- 三张表：
    simulations  每次仿真的一次性信息 + 性能指标
    records      逐轮记录（time/cwnd/ssthresh/state）
    events       关键事件（超时 / 快速重传）
- 单线程（Tkinter 主线程）使用，接口简单可靠
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime

from .config import DB_FILE


class SimulationDB:
    """SQLite 数据库封装：负责建库建表、保存仿真数据与查询。"""

    def __init__(self, db_path: str = DB_FILE) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # ------------------------------------------------------------------
    # 连接与建表
    # ------------------------------------------------------------------
    def connect(self) -> sqlite3.Connection:
        """建立连接（不存在则创建数据库文件），并初始化表结构。"""
        if self._conn is None:
            directory = os.path.dirname(os.path.abspath(self.db_path))
            os.makedirs(directory, exist_ok=True)
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            # WAL 模式：写入更快，读写并发更友好
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._create_tables()
        return self._conn

    def _create_tables(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS simulations (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                saved_at             TEXT    NOT NULL,
                ssthresh             REAL,
                rtt                  REAL,
                mss                  REAL,
                loss_rate            REAL,
                rounds               INTEGER,
                avg_throughput_mbps  REAL,
                congestion_count     INTEGER,
                timeout_count        INTEGER,
                dup_ack_count        INTEGER,
                switch_round         INTEGER,
                cwnd_peak            REAL,
                cwnd_valley          REAL,
                final_cwnd           REAL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS records (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id  INTEGER NOT NULL,
                time           INTEGER NOT NULL,
                cwnd           REAL    NOT NULL,
                ssthresh       REAL    NOT NULL,
                state          TEXT    NOT NULL,
                FOREIGN KEY (simulation_id) REFERENCES simulations(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                simulation_id  INTEGER NOT NULL,
                round_no       INTEGER NOT NULL,
                time           INTEGER NOT NULL,
                type           TEXT    NOT NULL,
                FOREIGN KEY (simulation_id) REFERENCES simulations(id)
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_records_sim ON records(simulation_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_events_sim ON events(simulation_id)")
        self._conn.commit()

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # 保存（每次仿真结束自动调用）
    # ------------------------------------------------------------------
    def save_simulation(
        self,
        config,
        stats: dict,
        records: list[dict],
        events: list[dict],
    ) -> int:
        """将一次仿真的配置、统计指标、逐轮记录与关键事件写入数据库。

        返回本次仿真的记录 ID（simulations.id）。
        """
        conn = self.connect()
        cur = conn.cursor()
        saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute(
            """
            INSERT INTO simulations (
                saved_at, ssthresh, rtt, mss, loss_rate, rounds,
                avg_throughput_mbps, congestion_count, timeout_count,
                dup_ack_count, switch_round, cwnd_peak, cwnd_valley, final_cwnd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                saved_at,
                config.ssthresh,
                config.rtt,
                config.mss,
                config.loss_rate,
                config.rounds,
                stats.get("平均吞吐量(Mbps)"),
                stats.get("拥塞发生次数"),
                stats.get("超时次数"),
                stats.get("快速重传次数"),
                stats.get("切换到拥塞避免的轮数"),
                stats.get("cwnd 峰值(MSS)"),
                stats.get("cwnd 谷值(MSS)"),
                stats.get("最终 cwnd(MSS)"),
            ),
        )
        sim_id = cur.lastrowid

        cur.executemany(
            "INSERT INTO records (simulation_id, time, cwnd, ssthresh, state) VALUES (?, ?, ?, ?, ?)",
            [
                (sim_id, r["time"], r["cwnd"], r["ssthresh"], r["state"])
                for r in records
            ],
        )
        cur.executemany(
            "INSERT INTO events (simulation_id, round_no, time, type) VALUES (?, ?, ?, ?)",
            [
                (sim_id, e["round"], e["time"], e["type"])
                for e in events
            ],
        )
        conn.commit()
        return sim_id

    # ------------------------------------------------------------------
    # 查询（供报告撰写与二次分析使用）
    # ------------------------------------------------------------------
    def list_simulations(self, limit: int = 10) -> list[sqlite3.Row]:
        """列出最近 limit 次仿真（按时间倒序）。"""
        conn = self.connect()
        return conn.execute(
            """
            SELECT id, saved_at, ssthresh, rtt, mss, loss_rate, rounds,
                   avg_throughput_mbps, congestion_count, timeout_count,
                   dup_ack_count, switch_round, cwnd_peak, cwnd_valley, final_cwnd
            FROM simulations ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()

    def get_records(self, simulation_id: int) -> list[sqlite3.Row]:
        """查询某次仿真的全部逐轮记录。"""
        conn = self.connect()
        return conn.execute(
            "SELECT time, cwnd, ssthresh, state FROM records WHERE simulation_id = ? ORDER BY time",
            (simulation_id,),
        ).fetchall()

    def get_events(self, simulation_id: int) -> list[sqlite3.Row]:
        """查询某次仿真的关键事件。"""
        conn = self.connect()
        return conn.execute(
            "SELECT round_no, time, type FROM events WHERE simulation_id = ? ORDER BY round_no",
            (simulation_id,),
        ).fetchall()
