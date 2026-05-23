import { test, expect, describe, afterEach } from "bun:test"
import { AnthropicProvider } from "../../src/providers/anthropic.ts"

const realFetch = globalThis.fetch
let observedUrl: string | undefined

afterEach(() => {
  globalThis.fetch = realFetch
  observedUrl = undefined
})

function stubAnthropicFetch(body: unknown, status = 200) {
  globalThis.fetch = (async (input: any) => {
    observedUrl = typeof input === "string" ? input : input?.url ?? input?.toString?.()
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    })
  }) as typeof fetch
}

describe("AnthropicProvider with custom baseUrl", () => {
  test("SDK hits ${baseUrl}/v1/messages when baseUrl is supplied", async () => {
    stubAnthropicFetch({
      id: "msg_1",
      type: "message",
      role: "assistant",
      content: [
        { type: "tool_use", id: "tu_1", name: "extract_fields",
          input: { name: "probe", score: 42 } },
      ],
      model: "glm-5-thinking",
      stop_reason: "tool_use",
      usage: { input_tokens: 10, output_tokens: 5,
        cache_creation_input_tokens: 0, cache_read_input_tokens: 0 },
    })

    const provider = new AnthropicProvider({
      apiKey: "fake",
      model: "glm-5-thinking",
      baseUrl: "https://gateway.example.com",
    })

    const res = await provider.complete({
      messages: [{ role: "user", content: "extract" }],
      tools: [{ name: "extract_fields", description: "",
        inputSchema: { type: "object", properties: { name: { type: "string" }, score: { type: "number" } } } }],
      toolChoice: { name: "extract_fields" },
    })

    expect(observedUrl).toBe("https://gateway.example.com/v1/messages")
    expect(res.toolCalls).toHaveLength(1)
    expect(res.toolCalls[0]!.arguments).toEqual({ name: "probe", score: 42 })
  })
})
