# Report Format

The final answer must contain exactly five level-1 headings and no extra level-1 headings.

# 1、故障摘要

Record these six points:

- 故障类型
- 崩溃进程/线程
- 重启原因
- 故障编码
- 触发时间点
- 关键结论, in one or two sentences

# 2、关键日志

Include 3 to 8 core log entries directly related to the crash. Each row must include timestamp and log content.

| 时间 | 日志内容 |
|---|---|

# 3、时间线

Sort by time ascending. Include at most 10 rows.

| 时间 | 真实日志 | 简介描述 |
|---|---|---|

# 4、根因分析

This section must explicitly separate:

- 事实
- 推理
- 不确定点

Give at least 1 and at most 3 root-cause candidates. Each candidate must include:

- 可能性: 高 / 中 / 低
- 判断依据
- 不确定点
- 验证方式

Candidate categories include but are not limited to:

- Memory jump / DDR error when ESR or FAR evidence supports it.
- Realtime task priority rush when Hungtask scenario 1 applies.
- ABBA deadlock when a cyclic lock chain is found.
- Too many non-realtime tasks when Hungtask scenario 2 and READY > 1000 apply.
- Driver or assertion failure when ESR is BRK and stack frames point to a driver path.

# 5、建议排查方向

Give engineering actions sorted by priority. Default to 3 to 6 rows. Each row must include target, action, and expected result.

| 优先级 | 目标 | 动作 | 预期结果 |
|---|---|---|---|

## Strictly Forbidden

- Do not output `<think>` or `</textarea>`.
- Do not output JSON as the final answer.
- Do not wrap the entire report in a code block.
- Do not add a sixth level-1 heading.
- Do not output more than 8 recommendations.
- Do not add explanation before the report or summary after the report.
