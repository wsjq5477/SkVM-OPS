# 1、故障摘要

- 故障类型: KERNEL_UNIMPLEMENTED_EXCEPTION
- 崩溃进程/线程: ufs_eh_worker
- 重启原因: N/A
- 故障编码: N/A
- 触发时间点: [6636931:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.965928][PANIC][ED_00]==== Exception Dump Start (signum: 5, masked: 0) ====
- 关键结论: Kernel exception in ufs_eh_worker with BRK-style ESR; Claude should validate the final root cause.

# 2、关键日志

| 时间 | 日志内容 |
|---|---|
| 2.965928 | [6636931:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.965928][PANIC][ED_00]==== Exception Dump Start (signum: 5, masked: 0) ==== |
| 2.965953 | [6636933:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.965953][PANIC][ED_00]Exception registers: |
| 2.965965 | [6636934:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.965965][PANIC][ED_00] ESR=f2000800 (EC=0x3c, IL=0x1, ISS=0x800), FAR=0000000000000000, ELR=00000005f46acc18 |
| 2.966006 | [6636938:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.966006][PANIC][ED_00]Thread info: |
| 2.966626 | [6636995:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.966626][PANIC][ED_00]Stack backtrace (pname=/bin/devhost.elf, pid=34): |

# 3、时间线

| 时间 | 真实日志 | 简介描述 |
|---|---|---|
| 2.965916 | [6636930:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.965916][ERROR][do_log_transaction:52] [1749962273.651643][ED_00][transaction start] now mono_time is [115066.722303] | Log transaction starts and provides the baseline mono time. |
| 2.965928 | [6636931:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.965928][PANIC][ED_00]==== Exception Dump Start (signum: 5, masked: 0) ==== | Kernel exception dump starts. |
| 2.965965 | [6636934:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.965965][PANIC][ED_00] ESR=f2000800 (EC=0x3c, IL=0x1, ISS=0x800), FAR=0000000000000000, ELR=00000005f46acc18 | Exception registers are printed. |
| 2.966006 | [6636938:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.966006][PANIC][ED_00]Thread info: | Crash thread information begins. |
| 2.966626 | [6636995:1]: pid=34   tid=189  comm=ufs_eh_worker    [2.966626][PANIC][ED_00]Stack backtrace (pname=/bin/devhost.elf, pid=34): | Stack backtrace begins. |

# 4、根因分析

事实:
- 崩溃线程为 `ufs_eh_worker`，ESR=`f2000800`，FAR=`0000000000000000`，ELR=`00000005f46acc18`。
- ESR 解码为 `BRK instruction`，置信度 `high`。
- 内存损坏脚本检测结果为 `False`，类型 `none`。
- Hungtask 检测结果为 `False`，死锁检测结果为 `False`。

推理:
- 可能性: medium
- 根因候选: UFS error handler hit a BRK/BUG_ON style exception while resetting/restoring UFS.
- 判断依据: Crash thread: ufs_eh_worker; ESR fault type: BRK instruction; Top stack frame includes ufshcd_reset_and_restore.

不确定点:
- The log snippet does not include source code context or hardware status history.
- 验证方式: Check UFS driver error-handler source around ufshcd_reset_and_restore and correlate with device I/O errors.

# 5、建议排查方向

| 优先级 | 目标 | 动作 | 预期结果 |
|---|---|---|---|
| P0 | UFS reset path | Inspect ufshcd_reset_and_restore around the reported PC/ELR and the BRK trigger path. | Confirm whether the exception is an intentional BUG_ON/assertion or an unexpected branch. |
| P1 | Storage hardware/link state | Correlate RX_FSM_STATE and UFS error-handler logs before the panic. | Determine whether link/device errors caused the reset path to execute. |
| P2 | Crash reproducibility | Collect a longer klog around the first UFS error and panic. | Provide enough context for final root-cause confirmation. |
