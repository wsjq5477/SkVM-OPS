export const meta = {
  name: 'hm-kernel-logs',
  description: 'Hongmeng kernel logs analysis workflow (完整版) - 包含所有场景判定和详细输出模板',
  phases: ['读取日志', '日志解析', 'Hungtask目标检测', 'Snapshot去重', '基准时间定位', 'Hungtask场景判定', 'ESR深度分析', '内存损坏分析', '死锁链追踪', '报告生成'],
}

// args 支持两种形式：
// 1. 字符串路径: "/home/jiqi/log.txt"
// 2. 对象: { logPath: "/home/jiqi/log.txt" } 或 { logContent: "日志内容" }
const LOG_PATH = typeof args === 'string'
  ? args
  : (args?.logPath || (args?.logContent?.startsWith?.('/') ? args?.logContent : null))

phase('读取日志')
const logContent = await agent(
  `读取鸿蒙内核日志文件。

文件路径：${LOG_PATH || '未提供路径，使用 args.logContent'}

请执行 bash 工具读取日志文件内容：
\`\`\`bash
cat "${LOG_PATH || ''}"
\`\`\`

如果文件过大（>1MB），先读取前2000行了解结构，然后提取关键部分：
- 搜索 "PANIC" 关键字找到崩溃位置
- 提取崩溃前后各500行作为分析范围
- 同时搜索 "ESR="、"FAR="、"ELR=" 提取寄存器信息

输出JSON：
{
  "logContent": "日志内容（如果是大型文件，包含崩溃相关部分）",
  "fullLogSize": "完整日志文件的总行数",
  "crashLineNumbers": ["崩溃相关的行号"]
}`,
  { schema: {
    type: 'object',
    properties: {
      logContent: { type: 'string' },
      fullLogSize: { type: 'string' },
      crashLineNumbers: { type: 'array', items: { type: 'string' } }
    },
    required: ['logContent']
  }}
)

const PANIC_TYPES = {
  KERNEL: ['HM_PANIC_KERNEL', 'HM_PANIC_DEVHOST', 'HM_PANIC_SYSMGR', 'HM_PANIC_ELFLOADER', 'HM_PANIC_OOM', 'HM_PANIC_INJECT'],
  WATCHDOG: ['HM_PANIC_HIGHDOG', 'HM_PANIC_LOWDOG', 'HM_APWDT_LOWDOG', 'HM_APWDT_HIGHDOG', 'HM_APWDT_HARDDOG', 'CHARGER_S_WDT'],
  GUARD: ['HGUARD_DEADLOCK', 'HGUARD_DEADSCHED', 'HGUARD_USER_CONFIG', 'HGUARD_HG_ABNORMAL'],
}

function detectPanicType(logContent) {
  for (const [category, types] of Object.entries(PANIC_TYPES)) {
    for (const type of types) {
      if (logContent.includes(type)) {
        return { category, type }
      }
    }
  }
  return { category: 'UNKNOWN', type: 'UNKNOWN' }
}

phase('日志解析')
const logInfo = await agent(
  `分析鸿蒙内核日志，提取关键信息。

分析内容：
1. 查找 "KERNEL UNIMPLEMENTED EXCEPTION" 或 "PANIC" 确认崩溃
2. 提取寄存器：ELR、ESR、FAR
3. 提取 reboot reason 和 reboot_code
4. 提取线程信息（tid, name, state, prio, rq）
5. 查找关键日志：
   - "trigger hungry warn" → 记录tid, state, prio, rq
   - "hguard-worker thread is abnormal"
   - "trigger locked"
   - "HGUARD_DEADLOCK"
   - "__dlist_bug"
6. 查找 Stack backtrace 或 KERNEL CALL STACK 调用栈

日志内容：
${logContent?.logContent || args.logContent || LOG_PATH}

输出JSON：
{
  "has_crash": true/false,
  "panic_category": "KERNEL|WATCHDOG|GUARD|UNKNOWN",
  "panic_type": "具体类型",
  "crash_thread": "线程信息",
  "crash_cpu": "CPU编号",
  "registers": { "elr": "", "esr": "", "far": "" },
  "reboot_codes": { "reason": "", "reboot_code": "" },
  "key_logs": ["关键日志条目"],
  "trigger_hungry_warn": { "tid": "", "state": "", "prio": "", "rq": "" },
  "has_hguard_abnormal": true/false,
  "has_trigger_locked": true/false,
  "has_deadlock": true/false,
  "has_dlist_bug": true/false,
  "call_stack": ["函数地址列表"]
}`,
  { schema: {
    type: 'object',
    properties: {
      has_crash: { type: 'boolean' },
      panic_category: { type: 'string' },
      panic_type: { type: 'string' },
      crash_thread: { type: 'string' },
      crash_cpu: { type: 'string' },
      registers: {
        type: 'object',
        properties: { elr: { type: 'string' }, esr: { type: 'string' }, far: { type: 'string' } }
      },
      reboot_codes: {
        type: 'object',
        properties: { reason: { type: 'string' }, reboot_code: { type: 'string' } }
      },
      key_logs: { type: 'array', items: { type: 'string' } },
      trigger_hungry_warn: {
        type: 'object',
        properties: { tid: { type: 'string' }, state: { type: 'string' }, prio: { type: 'string' }, rq: { type: 'string' } }
      },
      has_hguard_abnormal: { type: 'boolean' },
      has_trigger_locked: { type: 'boolean' },
      has_deadlock: { type: 'boolean' },
      has_dlist_bug: { type: 'boolean' },
      call_stack: { type: 'array', items: { type: 'string' } }
    },
    required: ['has_crash']
  }}
)

log(`Panic: ${logInfo?.panic_type || '未知'} (${logInfo?.panic_category || '未知'})`)

if (!logInfo?.trigger_hungry_warn?.tid && !logInfo?.has_hguard_abnormal && !logInfo?.has_trigger_locked) {
  if (logInfo?.panic_category === 'WATCHDOG' || logInfo?.panic_category === 'GUARD') {
    throw new Error(`分析失败: klog日志中未找到 "trigger hungry warn" 或 "hguard-worker thread is abnormal" 日志，无法确定饿死目标线程。请人工检查日志。`)
  }
}

phase('Snapshot去重')
const snapshotInfo = await agent(
  `分析 hm_snapshot.txt（如果args.snapshotContent存在）进行去重。

查找 "transaction start" 到 "transaction end" 之间的日志：
1. 只保留第一份完整事务日志
2. 确保被饿死线程的信息在该transaction区间内
3. 如果不在，向后查找包含该线程信息的transaction区间

去重后的线程信息应包含：
- 每个线程的 tid, name, state, prio, rq, sctime
- actv_cref 用于锁链追踪
- lock_wait 信息

输出JSON：
{
  "has_snapshot": true/false,
  "thread_count": 数量,
  "ready_count": READY状态线程数,
  "running_count": RUNNING状态线程数,
  "blocked_count": BLOCKED状态线程数,
  "transaction_range": { "start": "mono时间", "end": "mono时间" },
  "基准时间T": mono时间值,
  "threads": [{ "tid": "", "name": "", "state": "", "prio": "", "rq": "", "sctime": "", "actv_cref": "", "lock_wait": "" }]
}`,
  { schema: {
    type: 'object',
    properties: {
      has_snapshot: { type: 'boolean' },
      thread_count: { type: 'number' },
      ready_count: { type: 'number' },
      running_count: { type: 'number' },
      blocked_count: { type: 'number' },
      transaction_range: {
        type: 'object',
        properties: { start: { type: 'string' }, end: { type: 'string' } }
      },
      基准时间T: { type: 'string' },
      threads: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            tid: { type: 'string' },
            name: { type: 'string' },
            state: { type: 'string' },
            prio: { type: 'string' },
            rq: { type: 'string' },
            sctime: { type: 'string' },
            actv_cref: { type: 'string' },
            lock_wait: { type: 'string' }
          }
        }
      }
    },
    required: ['has_snapshot']
  }}
)

phase('基准时间定位')
const baseTimeInfo = await agent(
  `从snapshot日志中提取基准时间点。

查找 "transaction start" 关键字，提取其 mono time 作为基准时间 T。

格式示例：
transaction start, mono=1000000

基准时间用于计算sctime差值，判断是否超过90s/120s超时阈值。

输出JSON：
{
  "基准时间T": 数字,
  "计算方法": "sctime与T的差值"
}`,
  { schema: {
    type: 'object',
    properties: {
      基准时间T: { type: 'number' },
      计算方法: { type: 'string' }
    },
    required: ['基准时间T']
  }}
)

phase('Hungtask场景判定')
const hungerAnalysis = await agent(
  `根据检测到的Hungtask指标，进行6种场景的分类判定。

【决策树】

被饿死线程sctime差值 > 90s?
  ├─ state=READY
  │    ├─ rq=7 (实时任务)
  │    │    ├─ 冲高线程prio>=41 && 冲高线程prio>=饿死线程prio
  │    │    │    ├─ 亲和性完全相同 → 场景(1) 实时任务冲高
  │    │    │    └─ 亲和性不同 → 场景(1) 但标注"未找到完全相同亲和性"
  │    │    └─ 不满足 → 场景(4) 其他
  │    └─ rq=6 (非实时任务)
  │         ├─ READY/RUNNING线程数>1000 → 场景(2) 非实时任务过多
  │         └─ 不满足 → 场景(4) 其他
  └─ state=BLOCK
       ├─ 有lock_wait → 场景(3) 阻塞等待
       │    ├─ 持锁线程state=READY → 场景(5) 持锁READY被冲高
       │    ├─ 持锁线程state=RUNNING → 场景(6) 持锁冲高饿死
       │    └─ 持锁线程state=BLOCK → 递归追踪锁链
       └─ 无lock_wait → 场景(4) 其他

【场景(1) 实时任务冲高判定条件】
- 被饿死线程rq=7, state=READY, sctime差值>90s
- 冲高线程rq=7或31, prio>=41, prio>=饿死线程prio
- 冲高线程与饿死线程亲和性完全相同（来自extra_sched_info[]第二个数字）
- 冲高线程sctime差值>90s

【候选冲高线程评分规则】
1. 筛选: rq=7或31, prio>=41, state=RUNNING或READY
2. 评分:
   - 状态得分: RUNNING得15分, READY得10分
   - 亲和性匹配: 完全相同得15分, 覆盖得10分, 其他得0分
   - 运行时间: sctime差值>90s得10分, 60-90s得6分, <60s得2分
3. 按总分降序，取前8个

检测到的指标：
- trigger_hungry_warn: ${JSON.stringify(logInfo?.trigger_hungry_warn)}
- has_hguard_abnormal: ${logInfo?.has_hguard_abnormal}
- has_trigger_locked: ${logInfo?.has_trigger_locked}
- has_deadlock: ${logInfo?.has_deadlock}

Panic类型: ${logInfo?.panic_type || '未知'}

线程信息：
${JSON.stringify(snapshotInfo?.threads?.slice(0, 50))}

日志内容（用于深度分析）：
${logContent?.logContent || args.logContent || '未提供日志内容'}

输出JSON：
{
  "has_hungtask": true/false,
  "hungtask_type": "HIGHDOG|DEADLOCK|DEADSCHED|USER_CONFIG|none",
  "hungry_thread": { "tid": "", "name": "", "state": "", "prio": "", "rq": "", "sctime差值": "" },
  "scenario": "场景(1-6)或none",
  "is_abba_deadlock": true/false,
  "blocking_thread": { "tid": "", "name": "", "state": "", "prio": "" },
  "lock_chain": ["锁链追踪结果"],
  "candidate_rush_threads": [{ "name": "", "tid": "", "state": "", "prio": "", "亲和性": "", "CPU": "", "可疑度得分": "" }],
  "no_same_affinity_flag": true/false,
  "confidence": "high/medium/low",
  "analysis_details": "详细分析说明",
  "system_stats": { "ready_count": 0, "running_count": 0, "blocked_count": 0, "total_threads": 0 }
}`,
  { schema: {
    type: 'object',
    properties: {
      has_hungtask: { type: 'boolean' },
      hungtask_type: { type: 'string' },
      hungry_thread: {
        type: 'object',
        properties: { tid: { type: 'string' }, name: { type: 'string' }, state: { type: 'string' }, prio: { type: 'string' }, rq: { type: 'string' }, sctime差值: { type: 'string' } }
      },
      scenario: { type: 'string' },
      is_abba_deadlock: { type: 'boolean' },
      blocking_thread: {
        type: 'object',
        properties: { tid: { type: 'string' }, name: { type: 'string' }, state: { type: 'string' }, prio: { type: 'string' } }
      },
      lock_chain: { type: 'array', items: { type: 'string' } },
      candidate_rush_threads: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            name: { type: 'string' },
            tid: { type: 'string' },
            state: { type: 'string' },
            prio: { type: 'string' },
            亲和性: { type: 'string' },
            CPU: { type: 'string' },
            可疑度得分: { type: 'number' }
          }
        }
      },
      no_same_affinity_flag: { type: 'boolean' },
      confidence: { type: 'string' },
      analysis_details: { type: 'string' },
      system_stats: {
        type: 'object',
        properties: { ready_count: { type: 'number' }, running_count: { type: 'number' }, blocked_count: { type: 'number' }, total_threads: { type: 'number' } }
      }
    },
    required: ['has_hungtask']
  }}
)

log(`Hungtask场景: ${hungerAnalysis?.scenario || 'none'}, 类型: ${hungerAnalysis?.hungtask_type || 'none'}`)

phase('ESR深度分析')
const esrAnalysis = await agent(
  `深度解析ARM64 ESR寄存器。

【ESR格式】
- EC[31:26]: 异常类别
- IL[25]: 指令长度 (0=16bit, 1=32bit)
- ISS[24:0]: 异常特定信息
- DFSC[5:0]: 数据故障状态码

【EC字段解析】
- 0x0: Unknown/Illegal instruction → 代码损坏或DDR错误
- 0x15: SVC instruction
- 0x1C: PAC failure → 函数类型不匹配
- 0x20: Instruction Abort from lower EL
- 0x21: Instruction Abort without EL change
- 0x24: Data Abort from lower EL (user space)
- 0x25: Data Abort without EL change (kernel space)
- 0x2F: SError → 硬件错误或DDR问题
- 0x3C: BRK instruction → Intentional BUG_ON

【Translation Fault (0x25/0x96 family)】
- DFSC = 0x15: Translation fault, level 1
- DFSC = 0x16: Translation fault, level 2
- DFSC = 0x17: Translation fault, level 3

【FAR判断】
- FAR=0 或 <0x1000: null pointer access
- FAR > 0x1000: 有效地址，查看具体内存位置
- 如果FAR与某寄存器同页但只有1bit差异 → DDR单bit跳变

寄存器值：
- ESR: ${logInfo?.registers?.esr || 'N/A'}
- FAR: ${logInfo?.registers?.far || 'N/A'}
- ELR: ${logInfo?.registers?.elr || 'N/A'}

日志内容（用于ESR深度分析）：
${logContent?.logContent || args.logContent || '未提供日志内容'}

输出JSON：
{
  "esr_ec": "EC字段值",
  "esr_il": "IL字段值",
  "esr_iss": "ISS字段值",
  "esr_dfsc": "DFSC字段值(如有)",
  "fault_type": "异常类型",
  "fault_subtype": "子类型",
  "likely_cause": "最可能原因",
  "is_null_pointer": true/false,
  "is_code_corruption": true/false,
  "is_memory_jump": true/false,
  "is_ddr_error": true/false,
  "single_bit_jump_candidate": true/false,
  "confidence": "high/medium/low",
  "analysis_details": "详细分析"
}`,
  { schema: {
    type: 'object',
    properties: {
      esr_ec: { type: 'string' },
      esr_il: { type: 'string' },
      esr_iss: { type: 'string' },
      esr_dfsc: { type: 'string' },
      fault_type: { type: 'string' },
      fault_subtype: { type: 'string' },
      likely_cause: { type: 'string' },
      is_null_pointer: { type: 'boolean' },
      is_code_corruption: { type: 'boolean' },
      is_memory_jump: { type: 'boolean' },
      is_ddr_error: { type: 'boolean' },
      single_bit_jump_candidate: { type: 'boolean' },
      confidence: { type: 'string' },
      analysis_details: { type: 'string' }
    },
    required: ['fault_type']
  }}
)

log(`ESR分析: ${esrAnalysis?.fault_type || '未知'} - ${esrAnalysis?.likely_cause || ''}`)

phase('内存损坏分析')
const memCorruption = await agent(
  `深度分析内存损坏/踩内存问题。

【触发条件】
- 用户询问是否是内存跳变/DDR跳变
- 检测到ESR=0x0、ESR=0x96xxxxxx、__dlist_bug等指标
- 检测到SError (ESR=0x2F)

【分析方法】

阶段A: 判断是否是内核PANIC
- grep "PANIC" hm_klog.txt | head -20

阶段B: 定位第一次PANIC的ESR和FAR
- 使用第一次PANIC的信息（后续PANIC可能是连锁反应）

阶段C: 解析ESR判断访存异常类型
- 0x96xxxxxx: Instruction Abort from MMU translation (翻译故障)
- 0x92xxxxxx: Data Abort from MMU translation (数据访问翻译故障)
- 0x86xxxxxx: Instruction Abort, same namespace
- 0x82xxxxxx: Data Abort, same namespace

阶段D: FAR地址分析
- 比较FAR与相关寄存器的地址
- 如果在同一4KB page内但只有bit差异 → 单bit跳变

阶段E: dlist类型PANIC分析
- 搜索 __dlist_bug
- 提取 "should be" (预期值) 和 "but was" (实际值)
- 如果差异只有1-2个bit → 内存跳变的直接证据

日志内容（用于内存损坏分析）：
${logContent?.logContent || args.logContent || '未提供日志内容'}

dlist_bug检测: ${logInfo?.has_dlist_bug || false}

输出JSON：
{
  "has_memory_corruption": true/false,
  "corruption_type": "dlist|translation_fault|serror|null_pointer|code_corruption|none",
  "confidence": "high/medium/low",
  "first_panic_esr": "第一次PANIC的ESR",
  "first_panic_far": "第一次PANIC的FAR",
  "expected_value": "dlist预期值(如有)",
  "actual_value": "dlist实际值(如有)",
  "bit_diff_analysis": "bit差异分析",
  "single_bit_jump": true/false,
  "evidence": ["证据列表"],
  "details": "详细说明"
}`,
  { schema: {
    type: 'object',
    properties: {
      has_memory_corruption: { type: 'boolean' },
      corruption_type: { type: 'string' },
      confidence: { type: 'string' },
      first_panic_esr: { type: 'string' },
      first_panic_far: { type: 'string' },
      expected_value: { type: 'string' },
      actual_value: { type: 'string' },
      bit_diff_analysis: { type: 'string' },
      single_bit_jump: { type: 'boolean' },
      evidence: { type: 'array', items: { type: 'string' } },
      details: { type: 'string' }
    },
    required: ['has_memory_corruption']
  }}
)

log(`内存损坏: ${memCorruption?.has_memory_corruption ? memCorruption?.corruption_type + ' (' + memCorruption?.confidence + ')' : '未发现'}`)

phase('死锁链追踪')
const deadlockAnalysis = await agent(
  `如果检测到HGUARD_DEADLOCK，进行ABBA死锁链追踪。

【分析方法】
1. 查找 "trigger locked" 获取触发tid
2. 在snapshot中使用actv_cref搜索（不是tcb_cref）
3. 构建等待链: tid-1 → owner-1 → tid-2 → owner-2 → ...
4. 检测ABBA: 如果任何owner等于之前出现过的actv_cref，则确认死锁

【关键规则】
- lock_wait的owner表示当前线程正在等待的锁的持锁线程对象
- owner需要匹配另一线程的actv_cref（不是tcb_cref）
- 递归找持锁人：搜索actv_cref=owner值，向上找到name，该线程为持锁人
- 不断递归直到找到state不为BLOCK的线程

【输出格式】

死锁链追踪表：
| tid | name | lock_wait | owner | actv_cref |
|-----|------|-----------|-------|-----------|
| xxx | xxx | lock=xxx | owner值 | actv_cref值 |

死锁路径图：
tid=X (actv_cref=xxx)
  → 等待锁 xxx，该锁被 owner=xxx (tid=Y) 持有
tid=Y (actv_cref=xxx)
  → 等待锁 xxx，该锁被 owner=xxx (tid=Z) 持有
...
ABBA DEADLOCK: owner形成循环等待

日志内容（用于死锁分析）：
${logContent?.logContent || args.logContent || '未提供日志内容'}

has_deadlock: ${logInfo?.has_deadlock || false}

输出JSON：
{
  "has_deadlock": true/false,
  "is_abba_deadlock": true/false,
  "deadlock_chain": [{ "tid": "", "name": "", "lock_wait": "", "owner": "", "actv_cref": "" }],
  "deadlock_path": ["死锁路径描述"],
  "involved_threads": ["涉及的线程名"],
  "root_cause": "根因描述",
  "details": "详细分析"
}`,
  { schema: {
    type: 'object',
    properties: {
      has_deadlock: { type: 'boolean' },
      is_abba_deadlock: { type: 'boolean' },
      deadlock_chain: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            tid: { type: 'string' },
            name: { type: 'string' },
            lock_wait: { type: 'string' },
            owner: { type: 'string' },
            actv_cref: { type: 'string' }
          }
        }
      },
      deadlock_path: { type: 'array', items: { type: 'string' } },
      involved_threads: { type: 'array', items: { type: 'string' } },
      root_cause: { type: 'string' },
      details: { type: 'string' }
    },
    required: ['has_deadlock']
  }}
)

phase('报告生成')
const report = await agent(
  `生成鸿蒙内核日志分析最终报告。

【分析结果汇总】

1. Panic信息:
   - 类型: ${logInfo?.panic_type || '未知'}
   - 类别: ${logInfo?.panic_category || '未知'}
   - 崩溃线程: ${logInfo?.crash_thread || '未知'}
   - 崩溃CPU: ${logInfo?.crash_cpu || '未知'}

2. 寄存器:
   - ESR: ${logInfo?.registers?.esr || 'N/A'}
   - FAR: ${logInfo?.registers?.far || 'N/A'}
   - ELR: ${logInfo?.registers?.elr || 'N/A'}

3. ESR分析:
   - 异常类型: ${esrAnalysis?.fault_type || '未知'}
   - 可能原因: ${esrAnalysis?.likely_cause || '未知'}
   - null pointer: ${esrAnalysis?.is_null_pointer || false}
   - 代码损坏: ${esrAnalysis?.is_code_corruption || false}
   - 内存跳变: ${esrAnalysis?.is_memory_jump || false}
   - DDR错误: ${esrAnalysis?.is_ddr_error || false}
   - 单bit跳变候选: ${esrAnalysis?.single_bit_jump_candidate || false}

4. 内存损坏:
   - 检测到: ${memCorruption?.has_memory_corruption || false}
   - 类型: ${memCorruption?.corruption_type || 'none'}
   - 置信度: ${memCorruption?.confidence || 'N/A'}
   - 单bit跳变: ${memCorruption?.single_bit_jump || false}
   - bit差异分析: ${memCorruption?.bit_diff_analysis || 'N/A'}

5. Hungtask/死锁:
   - 检测到: ${hungerAnalysis?.has_hungtask || false}
   - 类型: ${hungerAnalysis?.hungtask_type || 'none'}
   - 场景: ${hungerAnalysis?.scenario || 'none'}
   - 饿死线程: ${hungerAnalysis?.hungry_thread?.name || '未知'} (tid=${hungerAnalysis?.hungry_thread?.tid || 'N/A'})
   - 阻塞线程: ${hungerAnalysis?.blocking_thread?.name || 'N/A'}
   - 锁链: ${hungerAnalysis?.lock_chain?.join(' → ') || '无'}
   - ABBA死锁: ${hungerAnalysis?.is_abba_deadlock || false}
   - 候选冲高线程数: ${hungerAnalysis?.candidate_rush_threads?.length || 0}
   - 未找到完全相同亲和性: ${hungerAnalysis?.no_same_affinity_flag || false}
   - 系统统计: READY=${hungerAnalysis?.system_stats?.ready_count || 0}, RUNNING=${hungerAnalysis?.system_stats?.running_count || 0}, BLOCKED=${hungerAnalysis?.system_stats?.blocked_count || 0}

6. 死锁分析:
   - 检测到: ${deadlockAnalysis?.has_deadlock || false}
   - ABBA死锁: ${deadlockAnalysis?.is_abba_deadlock || false}
   - 涉及线程: ${deadlockAnalysis?.involved_threads?.join(', ') || '无'}

7. 重启原因:
   - reason: ${logInfo?.reboot_codes?.reason || 'N/A'}
   - reboot_code: ${logInfo?.reboot_codes?.reboot_code || 'N/A'}

8. 关键日志:
${(logInfo?.key_logs || []).slice(0, 8).map((log, i) => `   ${i + 1}. ${log}`).join('\n')}

原始日志关键片段：
${(logContent?.logContent || args.logContent || '未提供日志内容').slice(0, 4000)}

【最终报告格式 - 严格5个一级标题】

# 1、故障摘要
按以下六点记录：
- 故障类型: ${logInfo?.panic_type || '未知'}
- 崩溃进程/线程: ${logInfo?.crash_thread || '未知'}
- 重启原因: ${logInfo?.reboot_codes?.reason || 'N/A'}
- 故障编码: ${logInfo?.reboot_codes?.reboot_code || 'N/A'}
- 触发时间点: ${logInfo?.key_logs?.[0] || '未知'}
- 关键结论: 根据分析结果给出1-2句话总结

# 2、关键日志
必须包含3-8条与崩溃直接相关的核心日志条目，每条包含时间戳和日志内容。
用表格格式：
| 时间 | 日志内容 |

# 3、时间线
按时间升序，最多10条。用表格格式：
| 时间 | 真实日志 | 简介描述 |

# 4、根因分析
本章节必须区分"事实""推理""不确定点"。
至少给出1个根因候选，最多3个。每个根因候选必须包含：
- 可能性：高/中/低
- 判断依据：列出支持证据
- 不确定点：列出无法确定的部分
- 验证方式：如何验证这个推测

根因候选包括但不限于：
- 内存跳变/DDR错误（如果ESR=0x0或translation fault）
- 实时任务冲高（如果场景(1)且未找到完全相同亲和性）
- ABBA死锁（如果死锁链形成循环）
- 非实时任务过多（如果场景(2)且READY>1000）

# 5、建议排查方向
本章节必须给工程可执行动作。建议按优先级排序。
默认3到6条，每条必须包含：目标、动作、预期结果。
用表格格式：
| 优先级 | 目标 | 动作 | 预期结果 |

【严格禁止】
- 输出<think>或</textarea>标签
- 输出JSON
- 代码块包裹整个报告
- 额外的一级标题（第6个）
- 超过8条建议
- 报告前解释或报告后总结`,
  { schema: {
    type: 'object',
    properties: {
      report: { type: 'string' }
    },
    required: ['report']
  }}
)

return {
  panic_type: logInfo?.panic_type,
  panic_category: logInfo?.panic_category,
  registers: logInfo?.registers,
  esr_analysis: esrAnalysis,
  memory_corruption: memCorruption,
  hungtask_analysis: hungerAnalysis,
  deadlock_analysis: deadlockAnalysis,
  report: report?.report,
}