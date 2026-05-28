# 分析契约

Analyzer 会输出一个 JSON object，顶层 key 如下：

- `input`：日志路径、行数、字节数、崩溃行号。
- `summary`：崩溃摘要，例如 fault type、crash thread、CPU 和寄存器。
- `events`：关键事件列表，用于报告的关键日志和时间线。
- `stack_frames`：解析到的调用栈帧。
- `detections`：确定性检测结果，例如 hungtask、deadlock、memory corruption。
- `handoff`：提供给 Claude 的紧凑事实集合。

最终报告应优先使用 analyzer 的 JSON 事实。如果字段缺失，应写 `N/A` 或说明不确定性。

脚本输出的是证据和候选，不是最终根因结论。最终判断仍由 Claude 根据证据完成。
