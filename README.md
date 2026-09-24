# TCP 拥塞控制算法仿真系统（TCP Reno）

《网络综合实践》课程设计 —— 基于 TCP 拥塞控制算法的仿真设计与实现。

用 Python + Tkinter + Matplotlib 实现 TCP Reno 拥塞控制机制的离散事件仿真与可视化，
可观察慢启动、拥塞避免、超时重传、快速重传/快速恢复过程中 **cwnd** 的动态演化。

## 环境要求

- Windows 11 / Linux / macOS
- Python 3.10+
- 依赖库：`matplotlib`、`tkinter`（标准库自带）

```bash
pip install matplotlib
```

## 运行

```bash
python main.py
```

## 功能清单

| 子系统 | 功能 |
| --- | ---- |
| 参数配置 | ssthresh / RTT / MSS / 丢包率 / 仿真轮数设置；空值、非数字、超范围合法性校验；默认参数；JSON 持久化（config.json，启动自动加载） |
| 拥塞控制仿真 | 状态初始化 cwnd=1 MSS、慢启动指数增长、拥塞避免线性增长、超时（ssthresh=max(cwnd/2,2)、cwnd=1）、3 个重复 ACK 快速重传/恢复（cwnd=ssthresh） |
| 网络模拟 | 按丢包率随机判定每轮事件：正常 ACK / 超时 / 三重重复 ACK |
| 数据记录与统计 | 逐轮记录 time/cwnd/ssthresh/state；关键事件记录；平均吞吐量、拥塞次数、切换轮数、cwnd 峰值谷值；CSV 导出 |
| 图形界面 | 参数输入区、开始/暂停/重置/单步、实时曲线（ssthresh 阈值线、阶段底色、事件标注）、状态显示、进度条、统计显示 |
| 曲线导出 | 保存 PNG（分辨率可调） |

## 项目结构

```
TCP/
├── main.py                 # 程序入口
├── config/
│   └── config.json         # 用户参数配置（启动自动加载，关闭自动保存）
├── csv/                    # 仿真数据 CSV 导出目录
├── images/                 # cwnd 曲线 PNG 保存目录
└── tcp_sim/
    ├── __init__.py
    ├── config.py           # 参数配置子系统（校验 + JSON 持久化）
    ├── controller.py       # 拥塞控制算法层（CongestionController 抽象基类 + Reno 实现）
    ├── network.py          # 网络模拟器（随机丢包）
    ├── engine.py           # 仿真引擎（状态机调度，按 RTT 推进）
    ├── recorder.py         # 数据记录器（记录、统计、CSV 导出）
    ├── plotter.py          # 绘图层（Matplotlib 动态绘图 + PNG 保存）
    └── gui.py              # 视图层（Tkinter 界面）
```

## 使用说明

1. 在左侧参数区设置 ssthresh、RTT、MSS、丢包率与仿真轮数（或直接使用默认值）。
2. 点击 **开始**：连续仿真，曲线实时刷新；点击 **暂停** 可保留当前状态；点击 **单步** 逐轮观察；点击 **重置** 清空数据。
3. 仿真结束后，右侧显示性能指标：平均吞吐量、拥塞发生次数（超时 + 快速重传）、
   切换到拥塞避免的轮数、cwnd 峰值/谷值。
4. 点击 **导出数据(CSV)** 保存逐轮记录，可用 Excel 二次分析；点击 **保存曲线(PNG)** 保存曲线图。
5. 点击 **保存配置(JSON)** 保存当前参数，下次启动自动加载；**恢复默认参数** 一键还原。

## 算法说明（按 RTT 离散推进）

- **慢启动**：`cwnd *= 2`（等效于每 ACK `cwnd += 1 MSS`），到达 ssthresh 后切换拥塞避免；
- **拥塞避免**：`cwnd += 1`（等效于每 ACK `cwnd += MSS²/cwnd`）；
- **超时**：`ssthresh = max(cwnd/2, 2)`、`cwnd = 1`，回到慢启动；
- **快速重传/恢复**：3 个重复 ACK 时 `ssthresh = max(cwnd/2, 2)`、`cwnd = ssthresh`，进入快速恢复，
  一个 RTT 后回到拥塞避免（避免 cwnd 直接归 1）。

网络模拟器按 `random() < loss_rate` 判定丢包；当 `cwnd >= 4` 时部分丢包表现为三重重复 ACK
（其余为超时），从而同时演示两种拥塞信号。
