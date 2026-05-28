# 分析契约

Analyzer 会输出一个 JSON object，顶层 key 如下：

- `input`：日志路径、行数、字节数、崩溃行号。
- `log_info`：崩溃事实、panic 类型、寄存器、重启码、关键日志、调用栈。
- `snapshot_info`：存在时的 snapshot/thread 数据。
- `base_time_info`：存在时的 baseline mono time。
- `hungtask_analysis`：确定性的 Hungtask 标记和场景提示。
- `esr_analysis`：ESR 字段解码和 fault 分类。
- `memory_corruption`：确定性的内存破坏指标。
- `deadlock_analysis`：确定性的死锁指标和链路数据。
- `report_data`：可直接用于报告的事实、时间线、根因候选和建议。
- `metrics`：耗时和大小指标。

尽可能使用 `report_data` 编写最终报告。如果某个值缺失，在第 4 节中写 `N/A` 或解释不确定性。

不要把脚本生成的 `root_cause_candidates` 当成最终真相。它们只是供 Claude 评估的候选项。
