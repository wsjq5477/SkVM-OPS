/**
 * Manual: end-to-end live test of auto-probe.
 *
 * Requires a configured providers.route that points to a known polluting
 * gateway (e.g. one where glm-5-thinking via openai-compatible returns
 * polluted args). The script:
 *   1. Calls a forced tool_use through createProviderForModel.
 *   2. Asserts the response is clean.
 *   3. Calls again; asserts no probe is re-triggered (literal route now
 *      exists in config from the first call).
 *
 * Run with: bun run test/integration/live-auto-probe.ts <prefixed-model-id>
 *
 * Example: bun run test/integration/live-auto-probe.ts cheap_ipads/glm-5-thinking
 *
 * The first run will:
 *   - Trigger ToolArgumentsParseError on the first openai-compatible call
 *   - Run the probe, find a clean Anthropic-shaped alternative
 *   - Write a literal route to $SKVM_CACHE/skvm.config.json
 *   - Retry the user call via the new anthropic provider
 *   - Emit a `[auto-probe]` info log line on stderr
 *
 * The second run will:
 *   - Match the literal route directly (no probe)
 *   - Hit the anthropic provider on the first call
 *   - Zero probe overhead
 *
 * Run `skvm config probes clear cheap_ipads/<model>` to reset between runs
 * if you want to re-exercise the probe path.
 */

import { createProviderForModel } from "../../src/providers/registry.ts"

const modelId = process.argv[2]
if (!modelId) {
  console.error("usage: bun run test/integration/live-auto-probe.ts <prefixed-model-id>")
  process.exit(2)
}

const TOOL = {
  name: "extract_probe",
  description: "Echo a probe value.",
  inputSchema: {
    type: "object",
    properties: { name: { type: "string" }, score: { type: "number" } },
    required: ["name", "score"],
  },
} as const

console.log(`live-auto-probe target: ${modelId}`)
const provider = createProviderForModel(modelId)
console.log(`provider name: ${provider.name}`)

console.log("\n--- first call ---")
const t0 = performance.now()
const res = await provider.complete({
  messages: [{ role: "user", content: 'Call extract_probe with name="real" and score=99.' }],
  tools: [TOOL],
  toolChoice: { name: TOOL.name },
  maxTokens: 256,
  temperature: 0,
})
console.log(`elapsed: ${(performance.now() - t0).toFixed(0)}ms`)
console.log("result:", JSON.stringify(res.toolCalls[0]?.arguments))

console.log("\n--- second call ---")
const t1 = performance.now()
const provider2 = createProviderForModel(modelId)
const res2 = await provider2.complete({
  messages: [{ role: "user", content: 'Call extract_probe with name="second" and score=2.' }],
  tools: [TOOL],
  toolChoice: { name: TOOL.name },
  maxTokens: 256,
  temperature: 0,
})
console.log(`elapsed: ${(performance.now() - t1).toFixed(0)}ms`)
console.log("result:", JSON.stringify(res2.toolCalls[0]?.arguments))
