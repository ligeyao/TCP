# -*- coding: utf-8 -*-
"""TCP 拥塞控制算法仿真系统（基于 TCP Reno）。

模块划分（模型—控制—视图）：
- 模型层：controller.py（拥塞控制算法）、network.py（网络模拟器）、recorder.py（数据记录）
- 控制层：engine.py（仿真引擎）
- 视图层：plotter.py（绘图）、gui.py（Tkinter 界面）
"""

__version__ = "1.0.0"
