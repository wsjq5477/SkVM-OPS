# 文本分析类 Skill 静态编译设计草案

状态：待对齐  
目标场景：自动日志解析 skill 优化  
参考技术：SkVM AOT 多 Pass 编译、JIT-boost 运行时固化、JIT-optimize 证据驱动优化
实现路线：重写独立系统；只借鉴 SkVM 的技术思想和工程分层，不复用现有 SkVM 代码。
目标运行环境：Claude skill。

## 已确认约束

1. 输入只支持文件路径，不支持目录批处理和直接粘贴文本作为第一版入口。
2. 输出报告有固定格式；编译器需要把该格式作为 report schema 或模板接入。
3. 第一版只支持英文日志。
4. 允许生成并随 skill 携带测试 fixtures；第一版暂不考虑脱敏。
5. 产物优先面向 Claude skill，而不是 Codex skill 或 Claude workflow。
6. 目标 Claude skill 目录结构采用标准形态：`SKILL.md + scripts/ + references/`。
7. 第一版样例日志为 `doc-skill-ops/test_log.txt`。

## 当前 Workflow 输入输出

参考文件：`doc-skill-ops/hm-kernel-logs.js`。

当前 workflow 的 `args` 支持三种输入形态：

1. 字符串路径：`"/home/jiqi/log.txt"`。
2. 对象路径：`{ logPath: "/home/jiqi/log.txt" }`。
3. 日志内容：`{ logContent: "日志内容" }`。

第一版重写后的 Claude skill 只保留前两种“文件路径”入口，并统一归一化为 `logPath`。`logContent` 仅作为迁移参考，不进入第一版运行接口。

当前 workflow 的主要阶段：

1. 读取日志。
2. 日志解析。
3. Hungtask 目标检测。
4. Snapshot 去重。
5. 基准时间定位。
6. Hungtask 场景判定。
7. ESR 深度分析。
8. 内存损坏分析。
9. 死锁链追踪。
10. 报告生成。

当前结构化中间输出：

| 阶段 | 输出对象 | 关键字段 |
|---|---|---|
| 读取日志 | `logContent` | `logContent`, `fullLogSize`, `crashLineNumbers` |
| 日志解析 | `logInfo` | `has_crash`, `panic_category`, `panic_type`, `crash_thread`, `crash_cpu`, `registers`, `reboot_codes`, `key_logs`, `trigger_hungry_warn`, `has_hguard_abnormal`, `has_trigger_locked`, `has_deadlock`, `has_dlist_bug`, `call_stack` |
| Snapshot 去重 | `snapshotInfo` | `has_snapshot`, `thread_count`, `ready_count`, `running_count`, `blocked_count`, `transaction_range`, `基准时间T`, `threads[]` |
| 基准时间定位 | `baseTimeInfo` | `基准时间T`, `计算方法` |
| Hungtask 场景判定 | `hungerAnalysis` | `has_hungtask`, `hungtask_type`, `hungry_thread`, `scenario`, `is_abba_deadlock`, `blocking_thread`, `lock_chain`, `candidate_rush_threads`, `no_same_affinity_flag`, `confidence`, `analysis_details`, `system_stats` |
| ESR 深度分析 | `esrAnalysis` | `esr_ec`, `esr_il`, `esr_iss`, `esr_dfsc`, `fault_type`, `fault_subtype`, `likely_cause`, `is_null_pointer`, `is_code_corruption`, `is_memory_jump`, `is_ddr_error`, `single_bit_jump_candidate`, `confidence`, `analysis_details` |
| 内存损坏分析 | `memCorruption` | `has_memory_corruption`, `corruption_type`, `confidence`, `first_panic_esr`, `first_panic_far`, `expected_value`, `actual_value`, `bit_diff_analysis`, `single_bit_jump`, `evidence`, `details` |
| 死锁链追踪 | `deadlockAnalysis` | `has_deadlock`, `is_abba_deadlock`, `deadlock_chain`, `deadlock_path`, `involved_threads`, `root_cause`, `details` |
| 报告生成 | `report` | `report` |

当前最终返回对象：

```json
{
  "panic_type": "...",
  "panic_category": "...",
  "registers": {},
  "esr_analysis": {},
  "memory_corruption": {},
  "hungtask_analysis": {},
  "deadlock_analysis": {},
  "report": "..."
}
```

当前固定报告格式为严格 5 个一级标题：

1. `# 1、故障摘要`
2. `# 2、关键日志`
3. `# 3、时间线`
4. `# 4、根因分析`
5. `# 5、建议排查方向`

报告约束：

- “关键日志”必须包含 3-8 条与崩溃直接相关的核心日志条目，每条包含时间戳和日志内容。
- “时间线”按时间升序，最多 10 条，字段为 `时间 | 真实日志 | 简介描述`。
- “根因分析”必须区分事实、推理、不确定点；至少 1 个根因候选，最多 3 个。
- “建议排查方向”默认 3-6 条，按优先级排序，字段为 `优先级 | 目标 | 动作 | 预期结果`。
- 禁止输出 `<think>`、`</textarea>`、JSON、包裹整个报告的代码块、额外一级标题、超过 8 条建议、报告前解释或报告后总结。

## 基于当前 Workflow 的静态/运行时划分

| Workflow 能力 | 第一版处理方式 | 说明 |
|---|---|---|
| `args` 输入归一化 | 静态脚本 | 只接受字符串路径或 `{ logPath }`，统一校验文件存在性和可读性。 |
| 大文件读取与崩溃窗口截取 | 静态脚本 | 文件超过阈值时，围绕 `PANIC`、`ESR=`、`FAR=`、`ELR=` 提取上下文窗口。 |
| Panic 类型检测 | 静态脚本 | `PANIC_TYPES` 是稳定枚举，可直接固化为 Python 常量和匹配函数。 |
| ELR/ESR/FAR、reboot code、关键 flag 提取 | 静态脚本 | 适合正则提取，输出结构化 `logInfo`。 |
| Snapshot transaction 去重 | 静态脚本 | `transaction start/end`、线程字段、`actv_cref`、`lock_wait` 解析可固化。 |
| 基准时间 `T` 与 `sctime` 差值计算 | 静态脚本 | 数值计算和阈值判断稳定，可直接单元测试。 |
| Hungtask 六类场景决策树 | 混合，优先脚本 | 决策树和候选冲高线程评分可脚本化；证据不足或字段缺失时交给 Claude 复核。 |
| ESR 位域解析 | 静态脚本 | EC/IL/ISS/DFSC 解码、FAR 阈值、常见异常类型映射可固化。 |
| 内存跳变/DDR 判断 | 混合 | bit diff、dlist `expected/actual` 可脚本化；最终“是否足以认定”为 Claude 语义判断。 |
| ABBA 死锁链追踪 | 混合，优先脚本 | 基于 `actv_cref -> owner -> tid` 的图追踪可脚本化；复杂缺失链路交给 Claude 解释。 |
| 五段式最终报告 | Claude skill | 脚本提供事实表和候选结论，Claude 按固定模板组织报告、区分事实/推理/不确定点。 |
| 失败回退 | Claude skill | 脚本输出结构化错误和低置信标记，Claude 决定如何提示人工检查。 |

## 背景

当前很多日志解析类 skill 以纯自然语言描述工作流：先读日志、识别格式、提取字段、归并事件、判断异常、输出报告。这类 skill 可读性高，但执行时容易把大量稳定步骤交给 LLM 反复推理，导致成本高、速度慢、结果不稳定。

本设计希望参考 SkVM 的思路，但不沿用 SkVM 现有代码。目标是重写一个面向“文本分析任务”的专用 skill 静态编译器：能确定、可测试、可重复的部分沉淀为 Python 脚本；仍需要语义判断、策略选择、异常解释的部分保留为 Claude skill 指令。最终产物不是完全替代 skill，而是一个“脚本 + 残余 Claude skill 指令 + 测试/证据”的混合 skill 包。

## 设计目标

1. 将自然语言 skill 中可固化的文本处理步骤转为 Python：
   - 文件路径输入校验、编码检测、文件读取、行切分、日志级别识别。
   - 时间戳、IP、trace id、request id、错误码、模块名等字段提取。
   - 正则匹配、结构化 JSON/CSV/kv 日志解析。
   - 去重、分组、排序、窗口统计、频次统计。
   - 输出 schema 校验和基础摘要生成。
2. 保留不适合固化的 Claude skill 工作：
   - 未知日志格式判断。
   - 跨行语义归因。
   - 根因假设、修复建议、风险解释。
   - 用户意图含混时的澄清和报告取舍。
   - 按固定报告格式组织最终输出。
3. 通过运行时证据降低误编译风险：
   - 使用真实对话日志、失败报告、重复工具调用轨迹、用户修正记录来判断哪些步骤确实反复出现。
   - 只有高频、低歧义、可验证的步骤进入 Python 脚本。
4. 输出 reviewable proposal：
   - 参考 SkVM `jit-optimize`，编译结果应先落入提案目录，用户审核后再接受。
   - 不直接覆盖原 skill。

## 非目标

1. 不做通用自然语言到任意程序的编译器。
2. 不把全部日志分析交给规则引擎；LLM 仍负责开放式解释和综合判断。
3. 不在第一阶段实现 UI、模型训练或在线长期记忆。
4. 不基于 SkVM 现有 AOT/JIT 管线开发；第一版是完全独立的文本分析 skill 专用优化流程。
5. 不复用 SkVM 的 TypeScript 模块、CLI、proposal 存储实现或 pass registry；这些只作为概念参考。
6. 第一版不支持目录批处理、粘贴文本输入、中文日志或中英混合日志。

## 核心概念

### TAC：Text Analysis Contract

类似 SkVM AOT 中的 SCR，TAC 是从自然语言 skill 中抽取的文本分析契约：

```json
{
  "inputs": ["log file path"],
  "outputSchema": {
    "panic_type": "string",
    "panic_category": "string",
    "registers": "object",
    "esr_analysis": "object",
    "memory_corruption": "object",
    "hungtask_analysis": "object",
    "deadlock_analysis": "object",
    "report": "string"
  },
  "entities": ["panic_type", "crash_thread", "crash_cpu", "ESR", "FAR", "ELR", "reboot_reason", "reboot_code", "tid", "thread_name", "state", "prio", "rq", "sctime", "actv_cref", "lock_wait"],
  "deterministicRules": ["read log file by path", "extract PANIC windows", "extract ESR/FAR/ELR", "extract reboot codes", "deduplicate snapshot transactions", "sort timeline by timestamp"],
  "semanticRules": ["classify Hungtask scenario", "interpret ESR likely cause", "judge memory corruption likelihood", "trace deadlock root cause", "write root-cause analysis in fixed report format"],
  "failureModes": ["file not found", "unsupported language", "unknown format", "mixed encodings", "missing timestamps"]
}
```

TAC 不要求一次完全准确。它的作用是让后续 Pass 有结构化输入，而不是反复读整篇 SKILL.md。

### Solidification Candidate

参考 SkVM JIT-boost 的 `BoostCandidate`，文本分析场景中的固化候选表示“某段自然语言流程可以变成一个确定性函数”：

```json
{
  "purposeId": "extract-log-events",
  "trigger": ["parse logs", "extract events", "timeline"],
  "inputTypes": ["file path"],
  "outputSchema": "events.schema.json",
  "implementation": "scripts/extract_events.py",
  "confidence": 0.86,
  "risk": "low",
  "residualReasoning": ["root cause ranking"]
}
```

候选必须同时满足三个条件：可用样例验证、可解释失败、失败时能回退到 LLM。

## 建议架构

### 静态识别与运行时优化边界

```text
+------------------------------------------------------------------+
| 静态识别 / 静态编译阶段                                           |
+------------------------------------------------------------------+
| 原始 Skill                                                        |
|   SKILL.md / references / scripts                                 |
|          |                                                       |
|          v                                                       |
| TAC 抽取                                                         |
|   输入、输出、实体、规则、失败模式                                |
|          |                                                       |
|          v                                                       |
| 可固化步骤识别                                                    |
|   正则、解析、统计、schema 校验                                   |
|          |                                                       |
|          v                                                       |
| Python 脚本生成                                                   |
|   analyze_logs.py / tests / schema                                |
|          |                                                       |
|          v                                                       |
| 残余 Claude Skill 指令重写                                        |
|   只保留语义判断和回退流程                                        |
|          |                                                       |
|          v                                                       |
| 可审核提案                                                        |
|   不直接覆盖原 Skill                                              |
+------------------------------------------------------------------+
                              |
                              v
+------------------------------------------------------------------+
| 运行时优化 / 证据闭环阶段                                         |
+------------------------------------------------------------------+
| 执行优化后的 Skill                                                |
|          |                                                       |
|          v                                                       |
| 运行 Python 脚本                                                   |
|   提取事件、统计、异常候选                                        |
|          |                                                       |
|          v                                                       |
| LLM 处理残余任务                                                   |
|   根因、解释、建议、取舍                                          |
|          |                                                       |
|          v                                                       |
| 记录运行证据                                                       |
|   对话日志、工具调用、失败报告、用户修正                          |
|          |                                                       |
|          v                                                       |
| 更新固化候选评分                                                   |
|   频率、稳定性、风险、回退能力                                    |
+------------------------------------------------------------------+
                              |
                              v
                  反馈给下一轮静态编译
```

边界原则：

- 静态阶段负责“识别并固化稳定流程”：从自然语言 skill 中抽取 TAC，判断哪些步骤可以变成脚本，并生成脚本、测试和残余 Claude skill 指令。
- 运行时阶段负责“执行、观测、再优化”：脚本先处理确定性文本分析，LLM 只处理开放式判断；执行证据回流到下一轮静态编译。
- 运行时不会即时改写 skill；它只积累证据和候选评分。真正改写仍发生在下一轮静态编译提案中。

```text
原始自然语言 Skill
  |
  v
Pass 1: TAC 抽取
  |
  v
Pass 2: 静态固化候选分析 <-------- 运行时证据 / 对话日志
  |                                      |
  v                                      v
Pass 3: 证据增强与风险评分
  |
  v
Pass 4: Python 脚本生成
  |
  v
Pass 5: 残余 Claude Skill 指令重写
  |
  v
Pass 6: 测试与 Guard
  |
  v
优化提案 Proposal
```

### Pass 1：TAC 抽取

输入：`SKILL.md`、references、已有 scripts 描述。  
输出：`text-analysis-contract.json`。

抽取内容包括输入来源、输出格式、实体字段、稳定规则、语义判断规则、失败处理策略、报告模板。该 Pass 可以使用 LLM，但输出必须走 JSON schema 校验。

### Pass 2：静态固化候选分析

输入：TAC 和原始 skill。  
输出：`solidification-candidates.json`。

该 Pass 将规则分成三类：

- `python-ready`：正则、解析、统计、schema 校验等确定性逻辑。
- `hybrid`：先脚本生成结构化证据，再由 LLM 做解释。
- `llm-only`：开放式判断、含混需求澄清、跨域推理。

第一版建议只实现 `python-ready` 和 `hybrid`，并显式拒绝高风险规则固化。

### Pass 3：运行时证据增强

输入：对话日志、失败报告、工具调用日志、用户修正记录。  
输出：带置信度和风险评分的候选列表。

评分依据：

- 频率：同类操作是否多次出现。
- 稳定性：输入变化时规则是否仍成立。
- 可验证性：是否能从样例构造测试。
- 失败成本：脚本误判是否会误导最终结论。
- 回退能力：脚本失败时 LLM 是否可以接管。

该 Pass 对应 SkVM JIT-optimize 的证据驱动思想，但目标不是直接改自然语言，而是决定哪些部分值得静态固化。

### Pass 4：Python 脚本生成

输出建议：

```text
scripts/
  analyze_logs.py          # CLI 入口
  extract_events.py        # 行级/块级事件抽取
  normalize.py             # 时间、级别、服务名、trace id 归一化
  aggregate.py             # 分组、排序、统计
  schema.py                # 输出 schema 和校验
tests/
  fixtures/
  test_extract_events.py
compiled/
  text-analysis-contract.json
  solidification-candidates.json
  compile-manifest.json
```

第一版脚本应尽量少而稳。推荐先生成一个 `scripts/analyze_logs.py` 作为统一入口，内部再拆模块，避免 skill 调用多个脚本时流程变复杂。

### Pass 5：残余 Claude Skill 指令重写

重写后的 `SKILL.md` 不再要求 agent 从零阅读所有日志，而是要求：

1. 先运行 `python scripts/analyze_logs.py --input <path> --out <json>`。
2. 读取脚本输出的结构化事件、统计、异常候选。
3. 只对 `needs_llm_review=true` 的项目做语义分析。
4. 在最终报告中区分“脚本提取事实”和“LLM 推断结论”。
5. 脚本失败、格式未知或置信度低时回退到原自然语言流程。

目标运行环境是 Claude skill，因此第 2-4 步都写入 `SKILL.md` 的过程指令，而不是产出 Claude workflow。

### Pass 6：测试与 Guard

必须生成最小验证集：

- 样例日志能被解析为预期事件数量。
- 时间戳排序稳定。
- JSONL、普通文本、混合多行错误至少各覆盖一个 fixture。
- 脚本失败时返回结构化错误，而不是静默输出空结果。
- 最终报告不得把 LLM 推断伪装成脚本事实。

Guard 规则：

- 不删除原 skill 的关键输出要求。
- 不把 `llm-only` 规则写入 Python。
- 不在脚本中硬编码用户私有路径。
- 第一版暂不启用脱敏流程；fixtures 可直接来自 `doc-skill-ops/test_log.txt`。

## 产物形态

优化后的 Claude skill 包建议长这样：

```text
auto-log-analysis/
  SKILL.md
  scripts/
    analyze_logs.py
  references/
    report-format.md
    output-schema.md
    known-log-patterns.md
  tests/
    fixtures/
    test_analyze_logs.py
  compiled/
    text-analysis-contract.json
    solidification-candidates.json
    compile-manifest.json
```

其中 `compiled/` 是机器生成的可审计中间产物；`references/` 是人类可维护的说明；`references/report-format.md` 从 `hm-kernel-logs.js` 的 5 段报告模板抽取；`scripts/` 是运行时直接使用的确定性能力。

## 与 SkVM 的关系

本系统与 SkVM 是“思想借鉴”关系，不是代码继承关系。

- 借鉴 AOT：采用多阶段静态分析与重写，但重新定义文本分析专用的 TAC、候选评分、脚本生成和残余 Claude skill 指令重写。
- 借鉴 JIT-boost：把运行时反复出现的日志解析动作识别为可固化候选，但用新的 Python 脚本生成与回退机制实现。
- 借鉴 JIT-optimize：使用失败日志、用户反馈和执行 evidence 驱动优化，但不调用 SkVM 的 optimizer、proposal 目录或 TypeScript 实现。
- 借鉴 proposal：保留“先生成可审核提案，用户接受后再覆盖 skill”的交付理念，但 proposal 格式和存储由新系统自己定义。

## 第一阶段建议切法

第一阶段不追求自动覆盖所有日志格式，只做一个可闭环 MVP：

1. 输入一个日志解析 Claude skill 目录、`hm-kernel-logs.js` 抽取出的固定报告格式模板和英文样例日志 `doc-skill-ops/test_log.txt`。
2. 生成 TAC。
3. 识别 3 类高置信固化点：时间戳/级别提取、事件列表生成、基础统计。
4. 生成 `scripts/analyze_logs.py` 和最小测试。
5. 重写 `SKILL.md`，要求先跑脚本，再按固定报告格式做语义总结。
6. 生成 proposal，不自动覆盖原 skill。

MVP 成功标准：

- 同一份日志重复运行输出稳定。
- LLM 上下文中不再需要粘贴全部原始日志，只需要脚本摘要和必要证据片段。
- 对明显异常日志，最终报告仍能引用原始行号或片段。
- 脚本无法解析时能清楚回退，而不是给出错误确定性结论。

## 开发输入状态

开发所需的第一版输入已经齐备：

1. 目标产物：标准 Claude skill，目录结构为 `SKILL.md + scripts/ + references/`。
2. Workflow 来源：`doc-skill-ops/hm-kernel-logs.js`。
3. 样例日志：`doc-skill-ops/test_log.txt`。
4. 脱敏策略：第一版暂不考虑脱敏。

## 推荐决策

建议第一版采用“独立专用编译器 + 类 proposal 审核交付”的路线。它不是 SkVM AOT 主链路的一部分，也不依赖现有 `rewrite-skill`、`bind-env`、`extract-parallelism` 三个 Pass。

验证有效后，也优先保持独立演进。只有在后续明确需要和 SkVM 集成时，才另起一份集成设计，而不是把第一版建立在 SkVM 代码之上。
