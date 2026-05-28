# HM Kernel Log Skill 评估

## 结果摘要

- Panic 类型：`KERNEL_UNIMPLEMENTED_EXCEPTION`（KERNEL）
- 崩溃线程：CPU `1` 上的 `ufs_eh_worker`
- 寄存器：ESR `f2000800`，FAR `0000000000000000`，ELR `00000005f46acc18`
- ESR fault 类型：`BRK instruction`；可能原因：类似 intentional breakpoint/BUG_ON 的异常。
- 确定性脚本检测到内存破坏：`False`（无）
- 确定性脚本检测到 Hungtask：`False`
- 确定性脚本检测到死锁：`False`

## 速度

- 优化 analyzer 在 15 次本地运行中的中位耗时：`2.627 ms`。
- 优化 analyzer 最小/最大耗时：`2.303 / 4.470 ms`。
- 纯文本 baseline skill 没有本地确定性运行时间；它需要真实 Claude 运行完整 workflow 和日志。

## Token 占用估算

- Baseline 估算输入 token：`3411`。
- 优化版估算输入 token：`1805`。
- 估算降幅：`47.1%`。

token 数使用 `chars / 4` 做本地估算，只用于同口径比较，不是 provider 计费 token。

## 质量说明

- 优化脚本会在 Claude 写报告前抽取稳定事实。
- Claude 仍负责根因表述、不确定性和工程建议。
- 对该样例，确定性证据指向 `ufs_eh_worker` 中的 BRK-style exception，堆栈位于 UFS reset/error-handler 路径。
