# SkillFlow 图编译器设计

状态：用户已认可设计；初始 graph-first 实现由 `docs/superpowers/plans/2026-05-29-skillflow-graph-compiler.md` 跟踪。

## 背景

当前通用文本 skill 编译器是 contract-first：

```text
skill/workflow + samples
  -> contract.json
  -> solidification.json
  -> generated Claude skill bundle
```

这个版本证明了“用 LLM 做编译器、用 Python 做确定性执行层”是可行的。但它缺少一个关键中间表示：原始自然语言 skill 的执行流。

对日志分析和其他文本分析 skill 来说，优化器不应该从 prose 直接跳到生成代码。它应该先构建一张可审计的执行逻辑图。这个图类似源码里的 code graph，但来源是自然语言指令。

## 目标

构建一个 graph-first 的文本分析 Claude skill 编译器。

编译器把自然语言 skill 或 workflow 转换成结构化的 `SkillFlow Graph`，按节点判断哪些可脚本化、哪些是混合、哪些必须保留给 LLM，再为稳定部分生成确定性 Python，并重写 Claude skill，让运行时工作拆分为快速脚本和剩余 LLM 推理。

## 非目标

- 不复用 SKVM 实现代码。
- 不把 HM kernel log 语义硬编码进通用编译器。
- 不把 BPMN 作为内部模型的必要格式。
- 不声称所有自然语言指令都能安全编译成代码。
- 不从文本分析中移除 LLM。LLM 仍然是语义编译器，也是需要判断时的运行时推理层。

## 当前步骤重审

| 当前步骤 | 现在做什么 | v2 中正确责任方 | v2 变化 |
| --- | --- | --- | --- |
| 读取源 skill/workflow 和样例 | 加载文件和样例文本 | 脚本 | 保持确定性。增加元数据、大小限制和 source ID。 |
| `extract_contract` | 直接抽取输入/输出 contract | LLM 加脚本验证 | 不再作为第一 pass。contract 应由图派生。 |
| 自然语言执行步骤抽取 | 隐含在 `extract_contract` 里 | LLM | 显式变成 `extract_flow_graph`。要求节点 ID、边、输入、输出和证据 span。 |
| 图验证 | 现在没有 | 脚本 | 增加 schema 验证、可达性检查、环检查、输入输出缺失检查和 source-span 检查。 |
| `find_solidification` | 粗略分类为 `python_ready`、`hybrid` 或 `llm_only` | 混合 | 按图节点运行。脚本给确定性模式打分，LLM 判断语义歧义。 |
| 生成 Python analyzer | LLM 生成完整 analyzer | LLM 加脚本验证 | 只为 script 节点和 hybrid 的预抽取部分生成代码。 |
| 生成测试 | LLM 生成测试 | 混合 | LLM 提出测试意图，脚本创建 fixture 接线并执行。 |
| 验证生成 bundle | 运行测试和 analyzer | 脚本 | 保留并扩展为 graph-to-code 覆盖验证。 |
| 修复 | 验证失败后 LLM 修复生成文件 | 脚本发现，LLM 修复 | 保留。把图验证和运行时失败作为编译器诊断喂给 LLM。 |
| 生成优化后的 `SKILL.md` | LLM 生成最终 skill | LLM 加模板检查 | 围绕图节点重写：先跑脚本，再执行剩余 LLM 节点。 |
| 运行时优化 | 很弱 | 脚本 trace 加 LLM 分析 | 增加运行时 trace，记录 miss、fallback、慢节点和错误抽取。 |

## 核心概念：SkillFlow Graph

`SkillFlow Graph` 是编译器的核心中间表示。

它不是实体知识图谱，而是自然语言 skill 的执行流图。它应回答：

- 这个 skill 执行哪些步骤？
- 每个步骤消费和产生哪些数据？
- 哪些步骤是顺序、条件、循环或 fallback 路径？
- 哪些步骤足够确定，可以脚本化？
- 哪些步骤需要 LLM 判断？
- 每个节点由原始指令中的哪些内容支撑？

示例形态：

```json
{
  "graph_id": "hm-kernel-log-analysis",
  "entry_nodes": ["load_input"],
  "exit_nodes": ["write_report"],
  "nodes": [
    {
      "id": "extract_panic_facts",
      "type": "extract",
      "description": "Extract panic type, crash thread, CPU, ESR, FAR, ELR, and call stack.",
      "inputs": ["log_text"],
      "outputs": ["panic_facts"],
      "owner": "script_candidate",
      "determinism": "high",
      "evidence_spans": [
        {
          "source": "SKILL.md",
          "quote": "Extract crash context and key registers before root-cause analysis."
        }
      ]
    },
    {
      "id": "infer_root_cause",
      "type": "reason",
      "description": "Infer likely root cause from extracted facts and uncertainty.",
      "inputs": ["panic_facts", "timeline"],
      "outputs": ["root_cause_hypothesis"],
      "owner": "llm_required",
      "determinism": "low"
    }
  ],
  "edges": [
    {
      "from": "extract_panic_facts",
      "to": "infer_root_cause",
      "kind": "data_dependency"
    }
  ]
}
```

## 节点类型

第一版应保持类型系统足够小：

| 类型 | 含义 | 典型责任方 |
| --- | --- | --- |
| `load_input` | 读取用户提供的文件路径并规范化文本 | 脚本 |
| `chunk` | 切分或窗口化大文本 | 脚本 |
| `extract` | 抽取实体、时间戳、段落、计数器、堆栈、键值事实 | 脚本或混合 |
| `normalize` | 规范化名称、时间戳、严重级别、路径、代码 | 脚本 |
| `filter` | 选择相关行或事件 | 脚本 |
| `aggregate` | 计数、分组、排序、去重、按 key 关联 | 脚本 |
| `classify` | 将文本分类到已知标签 | 混合 |
| `decide` | 应用显式阈值或决策规则 | 脚本或混合 |
| `reason` | 解释原因、评估不确定性、连接弱信号 | LLM |
| `report` | 生成最终面向用户的报告 | LLM，可由模板辅助 |
| `validate` | 检查 schema、完整性、置信度或缺失证据 | 脚本 |
| `fallback` | 确定性抽取失败时路由到 LLM 或人工路径 | 混合 |

## 边类型

| 边类型 | 含义 |
| --- | --- |
| `sequence` | B 通常在 A 后执行 |
| `data_dependency` | B 消费 A 的输出 |
| `condition_true` | 条件为真时的分支 |
| `condition_false` | 条件为假时的分支 |
| `loop` | 对 chunk、事件、段落或候选项重复执行 |
| `fallback` | 前一个节点失败或置信度低时的恢复路径 |
| `evidence` | 从源指令或样例观察链接到节点 |
| `refinement` | 后续运行时反馈修正之前的静态决策 |

## 修订后的编译器流水线

```text
source skill/workflow + samples
        |
        v
ingest_sources                      [script]
        |
        v
extract_flow_graph                  [LLM]
        |
        v
validate_flow_graph                 [script]
        |
        v
derive_contract                     [script + LLM supplement]
        |
        v
classify_solidification_by_node     [script + LLM]
        |
        v
generate_deterministic_artifacts    [LLM]
        |
        v
validate_generated_bundle           [script]
        |
        v
repair_until_valid                  [script diagnostics + LLM repair]
        |
        v
rewrite_skill_around_graph          [LLM + template checks]
        |
        v
runtime_trace                       [script]
        |
        v
next_round_optimization             [script + LLM]
```

## 静态与运行时职责

静态编译负责：

- 从自然语言 skill 抽取 SkillFlow Graph。
- 验证图结构和来源 grounding。
- 派生输入、输出和报告 contract。
- 按确定性和可脚本化程度分类节点。
- 为确定性节点生成 Python。
- 生成测试和 fixture 期望。
- 输出优化后的 Claude skill bundle。

运行时优化负责：

- 记录哪些图节点运行了。
- 记录 analyzer 耗时和抽取置信度。
- 记录缺失字段和 fallback 原因。
- 为 Claude 保留紧凑 handoff JSON。
- 收集失败案例用于下一轮编译。
- 当运行样例足够多时，建议新的可脚本化模式。

## LLM 与脚本分工规则

当操作需要语义解释时使用 LLM：

- 理解自然语言指令。
- 把 prose 拆成有意义的分析步骤。
- 推断步骤之间的隐式依赖。
- 判断一条规则是否足够明确、可以脚本化。
- 根据图节点生成 Python 和测试。
- 在 `SKILL.md` 中编写剩余推理指令。
- 解释语义类运行时失败，而不是机械错误。

当操作是机械、可检查或可重复时使用脚本：

- 文件加载和样例管理。
- JSON schema 验证。
- 图可达性和边验证。
- 模式已知后的 regex 抽取。
- 时间戳解析、排序、分组、计数、去重。
- 运行测试。
- 测量速度和 token 估算。
- 捕获运行时 trace。
- 检查生成的 skill bundle 结构。

当 LLM 可以定义语义规则，而脚本可以执行规则时使用混合处理：

- LLM 识别抽取目标和候选模式。
- 脚本实现并验证抽取。
- 优化后的 skill 在置信度低时保留 LLM fallback。

## 输出布局

优化后的输出应包含 graph-first 编译器产物：

```text
<out>/
  SKILL.md
  scripts/
    analyze_text.py
  references/
    analysis-contract.md
    flow-graph.md
    report-format.md
  tests/
    test_analyze_text.py
  samples/
    ...
  compiled/
    source_manifest.json
    flow_graph.raw.json
    flow_graph.json
    graph_validation.json
    contract.json
    solidification.json
    generation.json
    validation.json
    runtime_trace.schema.json
  evaluation/
    baseline-vs-optimized.json
    baseline-vs-optimized.md
```

## 为什么内部不使用 BPMN

BPMN 和 process mining 是有用参考，但不是这个编译器的最佳内部模型。

BPMN 擅长业务流程控制流。本项目还需要额外字段，而 BPMN 不能自然表达：

- LLM-only 推理节点。
- 可脚本化程度和确定性分数。
- 来自 `SKILL.md` 的来源证据 span。
- 测试覆盖元数据。
- 运行时抽取置信度。
- fallback 原因。
- token 和速度优化指标。

编译器后续可以导出简化 BPMN、DOT 或 Mermaid 视图供人检查，但内部模型应是 `SkillFlow Graph`。

## 业界与研究对齐

该设计与几个既有方向相关：

- 从自然语言文本生成过程模型。Fabian Friedrich、Jan Mendling 和 Frank Puhlmann 在 CAiSE 2011 发表了 "Process Model Generation from Natural Language Text"：
  https://dblp.uni-trier.de/rec/conf/caise/FriedrichMP11.html
- Text-to-BPMN 抽取。2024 年一篇开放论文描述了使用 NLP、spaCy、BERT 和 GPT 模型从文本描述抽取 BPMN 模型：
  https://www.sciencedirect.com/science/article/pii/S187705092401439X
- 用 LLM prompt 抽取过程模型信息。该工作面向从流程描述中抽取活动、参与者和关系：
  https://arxiv.org/abs/2407.18540
- 程序性知识图谱抽取。该方向从 procedure 文本中抽取步骤、动作、对象、设备和时间信息：
  https://arxiv.org/abs/2412.03589 和
  https://github.com/cefriel/procedural-kg-llm
- 带结构和逻辑修正的 procedural graph extraction。这个方向接近本设计，因为它使用抽取、结构反馈和语义反馈循环：
  https://arxiv.org/abs/2601.19170
- PM4Py。适合借鉴运行时 trace 和 process mining 思路，但它从事件日志工作，不是从自然语言 skill 文本工作：
  https://github.com/process-intelligence-solutions/pm4py
- LangGraph。可作为未来图执行目标，但它不解决自然语言到图的抽取：
  https://docs.langchain.com/oss/python/langgraph/workflows-agents
- DSPy。它有类似编译器的思想，但优化的是 LLM 程序 prompt 和模块，不是把自然语言 skill 编译成确定性脚本：
  https://arxiv.org/abs/2310.03714

本项目填补的是更窄、更实用的空白：把自然语言文本分析 skill 编译成可审计执行流图，并在安全时生成确定性 Python。

## 验证策略

图验证：

- JSON schema 必须通过。
- 每个节点必须有 ID、类型、描述、责任方、输入和输出。
- 入口和出口节点必须存在。
- 非入口节点应该可达。
- 非出口节点应流向至少一个后续节点，除非标记为 terminal。
- 条件边必须命名 predicate。
- 可脚本化节点必须有测试义务。
- LLM-required 节点必须保留足够输入上下文供 Claude 推理。

生成产物验证：

- 标准 Claude skill 布局必须存在。
- 生成的 Python 测试必须通过。
- analyzer 必须能在每个样例上运行。
- analyzer 输出必须匹配派生 handoff schema。
- 在可能时，handoff JSON 应小于传递完整源文本。
- `SKILL.md` 必须提到 analyzer 路径和剩余 LLM 职责。

运行时验证：

- trace 文件必须是 JSONL 且 schema 合法。
- 每个 trace event 应包含图节点 ID、状态、耗时，以及适用时的 fallback 原因。
- 失败抽取应该可作为未来 fixture 重放。

## 风险与缓解

| 风险 | 缓解 |
| --- | --- |
| LLM 编造 skill 中没有的步骤 | 要求 evidence spans，并在图验证中标记无支撑节点。 |
| 图结构合法但语义错误 | 增加 LLM 语义复审 pass 和基于样例的验证。 |
| 过度固化移除了有价值的推理 | 保留置信度阈值和 LLM fallback 路径。 |
| 生成的 Python 只通过一个样例但泛化差 | 随时间要求多个样例和运行时 trace 反馈。 |
| 图变得过于复杂 | 从小型节点/边 taxonomy 开始，避免追求 BPMN 级完整性。 |
| 本地模型输出 malformed JSON | 保持严格 JSON 解析、重试和测试用 mock fixture。 |

## 实施阶段

阶段 1：图 IR 和编译器 pass 拆分

- 增加 `extract_flow_graph`。
- 增加 `flow_graph.json` schema 验证。
- 从图派生 `contract.json`。
- 在新 graph pass 后保持现有生成流程可用。

阶段 2：节点级固化

- 用逐节点分类替换粗粒度候选项分类。
- 增加可脚本化打分。
- 生成 `flow-graph.md` 供人工 review。

阶段 3：图感知产物生成

- 只为可脚本化节点生成 Python。
- 为 LLM 节点生成剩余 `SKILL.md` 指令。
- 增加 graph-to-code 覆盖检查。

阶段 4：运行时 tracing

- 增加 trace schema。
- 让生成的 analyzer 发出节点级 trace event。
- 将运行时失败喂给 repair 或下一轮 compilation。

阶段 5：可视化和可选导出

- 导出 DOT 或 Mermaid 图。
- 可选导出简化的类 BPMN 视图。
- 不把 BPMN 作为内部表示。

## 成功标准

- 编译器能为新的文本分析 skill 输出合法 `flow_graph.json`。
- 每个生成的脚本函数都能映射回一个或多个图节点。
- 优化后的 skill 清楚说明哪些图节点由 Python 处理，哪些仍是 LLM 职责。
- 单元测试使用 mock graph 响应即可通过，不需要真实 LLM。
- 本地 OpenAI-compatible 模型可以运行真实流水线。
- runtime trace 能识别慢节点、失败节点或 fallback 高频节点。
- 设计保持通用，不依赖 HM-kernel 特定逻辑。
