# -*- coding: utf-8 -*-
"""参数配置子系统：仿真参数的定义、合法性校验、默认参数与 JSON 持久化。

文档要求（3.3.1）：
- 慢启动阈值 ssthresh 设置
- RTT 时延设置
- MSS 大小设置
- 丢包率设置
- 仿真轮数设置
- 参数合法性校验（空值、非数字、超范围则提示并阻止启动）
- 默认参数与持久化（JSON 保存，下次启动自动加载）
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict

# 参数取值范围
PARAM_RULES = {
    "ssthresh": {"min": 2, "max": 100000, "type": int, "label": "慢启动阈值 ssthresh"},
    "rtt": {"min": 1, "max": 100000, "type": float, "label": "RTT 时延(ms)"},
    "mss": {"min": 1, "max": 65535, "type": int, "label": "MSS 大小(字节)"},
    "loss_rate": {"min": 0.0, "max": 1.0, "type": float, "label": "随机丢包率"},
    "rounds": {"min": 1, "max": 100000, "type": int, "label": "仿真轮数"},
}

# 默认参数（文档 3.3.1 (7)：系统提供一组合理默认参数）
DEFAULT_PARAMS = {
    "ssthresh": 32,       # MSS
    "rtt": 100.0,         # ms
    "mss": 1460,          # 字节（以太网典型 MSS）
    "loss_rate": 0.02,    # 2% 丢包率
    "rounds": 100,        # 仿真 100 轮
}

# 项目根目录（TCP/）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 三个专用存放目录：配置 / CSV / 仿真图片
CONFIG_DIR = os.path.join(BASE_DIR, "config")
CSV_DIR = os.path.join(BASE_DIR, "csv")
IMAGES_DIR = os.path.join(BASE_DIR, "images")

# 配置文件路径：config/config.json
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def ensure_dirs() -> None:
    """确保三个专用目录存在（不存在则创建）。"""
    for directory in (CONFIG_DIR, CSV_DIR, IMAGES_DIR):
        os.makedirs(directory, exist_ok=True)


@dataclass
class SimulationConfig:
    """仿真参数配置对象。"""

    ssthresh: int = DEFAULT_PARAMS["ssthresh"]
    rtt: float = DEFAULT_PARAMS["rtt"]
    mss: int = DEFAULT_PARAMS["mss"]
    loss_rate: float = DEFAULT_PARAMS["loss_rate"]
    rounds: int = DEFAULT_PARAMS["rounds"]

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def validate(self) -> list[str]:
        """校验全部参数，返回错误信息列表（空列表表示全部合法）。

        校验规则（文档 3.4.1 安全需求）：
        拦截空值、负数、非数字、超范围等非法输入。
        """
        errors: list[str] = []
        for name, rule in PARAM_RULES.items():
            value = getattr(self, name)
            label = rule["label"]
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"{label} 不能为空")
                continue
            try:
                value = rule["type"](value)
            except (TypeError, ValueError):
                errors.append(f"{label} 必须为数字")
                continue
            if value < rule["min"] or value > rule["max"]:
                errors.append(f"{label} 超出范围 [{rule['min']}, {rule['max']}]")
                continue
            # 类型修正（例如 float 型参数传入字符串 "100"）
            setattr(self, name, value)
        return errors

    @classmethod
    def from_strings(cls, ssthresh: str, rtt: str, mss: str, loss_rate: str, rounds: str) -> "SimulationConfig":
        """从界面输入框的字符串构造配置对象（非法字符串保留原值，由 validate 统一拦截）。"""
        def _to_number(text: str, rule: dict):
            text = text.strip()
            if not text:
                return None
            try:
                return rule["type"](text)
            except ValueError:
                return text  # 保留原字符串，让 validate 给出"必须为数字"的提示

        return cls(
            ssthresh=_to_number(ssthresh, PARAM_RULES["ssthresh"]),
            rtt=_to_number(rtt, PARAM_RULES["rtt"]),
            mss=_to_number(mss, PARAM_RULES["mss"]),
            loss_rate=_to_number(loss_rate, PARAM_RULES["loss_rate"]),
            rounds=_to_number(rounds, PARAM_RULES["rounds"]),
        )

    # ------------------------------------------------------------------
    # JSON 持久化（文档 3.3.1 (7)）
    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationConfig":
        params = dict(DEFAULT_PARAMS)
        if isinstance(data, dict):
            for key in params:
                if key in data:
                    params[key] = data[key]
        return cls(**params)

    def save_json(self, path: str = CONFIG_FILE) -> None:
        """将当前配置保存为 JSON 文件。"""
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_json(cls, path: str = CONFIG_FILE) -> "SimulationConfig":
        """从 JSON 文件加载配置；文件不存在或损坏时返回默认配置。"""
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = cls.from_dict(data)
            # 加载后同样做一次类型与范围修正
            if not cfg.validate():
                return cfg
        except (json.JSONDecodeError, OSError, ValueError):
            pass
        return cls()
