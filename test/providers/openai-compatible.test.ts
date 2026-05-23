import { test, expect, describe, beforeEach, afterEach } from "bun:test"
import { OpenAICompatibleProvider } from "../../src/providers/openai-compatible.ts"
import {
  ProviderHttpError,
  ProviderAuthError,
  ProviderNetworkError,
  isProviderError,
} from "../../src/providers/errors.ts"

/** A canned OpenAI-shaped /chat/completions response, including cache details. */
const TEXT_ONLY_RESPONSE = {
  id: "chatcmpl-abc",
  object: "chat.completion",
  created: 1,
  model: "gpt-4o",
  choices: [
    {
      index: 0,
      message: { role: "assistant", content: "hello world" },
      finish_reason: "stop",
    },
  ],
  usage: {
    prompt_tokens: 100,
    completion_tokens: 7,
    total_tokens: 107,
    prompt_tokens_details: { cached_tokens: 40 },
  },
}

const TOOL_CALL_RESPONSE = {
  id: "chatcmpl-xyz",
  object: "chat.completion",
  choices: [
    {
      index: 0,
      message: {
        role: "assistant",
        content: "",
        tool_calls: [
          {
            id: "call_1",
            type: "function",
            function: {
              name: "extract_fields",
              arguments: '{"name":"skvm","score":0.92}',
            },
          },
        ],
      },
      finish_reason: "tool_calls",
    },
  ],
  usage: {
    prompt_tokens: 50,
    completion_tokens: 20,
    total_tokens: 70,
  },
}

const realFetch = globalThis.fetch
let lastRequest: { url: string; init: RequestInit } | undefined

function stubFetch(responseBody: unknown, status = 200) {
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    lastRequest = { url: typeof url === "string" ? url : url.toString(), init: init ?? {} }
    return new Response(
      typeof responseBody === "string" ? responseBody : JSON.stringify(responseBody),
      { status, headers: { "Content-Type": "application/json" } },
    )
  }) as typeof fetch
}

function stubFetchThrow(error: unknown) {
  globalThis.fetch = (async () => {
    throw error
  }) as unknown as typeof fetch
}

beforeEach(() => {
  lastRequest = undefined
})

afterEach(() => {
  globalThis.fetch = realFetch
})

describe("OpenAICompatibleProvider.complete", () => {
  test("maps text response with cache tokens into TokenUsage", async () => {
    stubFetch(TEXT_ONLY_RESPONSE)
    const provider = new OpenAICompatibleProvider({
      apiKey: "fake",
      model: "gpt-4o",
      baseUrl: "https://api.example.com/v1",
    })

    const res = await provider.complete({ messages: [{ role: "user", content: "hi" }] })

    expect(res.text).toBe("hello world")
    expect(res.toolCalls).toEqual([])
    // prompt_tokens (100) minus cached_tokens (40) = 60 fresh input
    expect(res.tokens).toEqual({ input: 60, output: 7, cacheRead: 40, cacheWrite: 0 })
    expect(res.costUsd).toBeUndefined()
    expect(res.stopReason).toBe("end_turn")
  })

  test("parses tool_calls with JSON-encoded arguments", async () => {
    stubFetch(TOOL_CALL_RESPONSE)
    const provider = new OpenAICompatibleProvider({
      apiKey: "fake",
      model: "gpt-4o",
      baseUrl: "https://api.example.com/v1",
    })

    const res = await provider.complete({
      messages: [{ role: "user", content: "extract" }],
      tools: [{ name: "extract_fields", description: "", inputSchema: {} }],
    })

    expect(res.toolCalls).toHaveLength(1)
    expect(res.toolCalls[0]!.name).toBe("extract_fields")
    expect(res.toolCalls[0]!.arguments).toEqual({ name: "skvm", score: 0.92 })
    expect(res.stopReason).toBe("tool_use")
  })

  test("hits {baseUrl}/chat/completions with trailing slash normalized", async () => {
    stubFetch(TEXT_ONLY_RESPONSE)
    const provider = new OpenAICompatibleProvider({
      apiKey: "k",
      model: "m",
      baseUrl: "https://api.example.com/v1/",
    })

    await provider.complete({ messages: [{ role: "user", content: "hi" }] })

    expect(lastRequest?.url).toBe("https://api.example.com/v1/chat/completions")
  })

  test("request body does NOT include OpenRouter-specific fields", async () => {
    stubFetch(TEXT_ONLY_RESPONSE)
    const provider = new OpenAICompatibleProvider({
      apiKey: "k",
      model: "m",
      baseUrl: "https://api.example.com/v1",
    })

    await provider.complete({ messages: [{ role: "user", content: "hi" }] })

    const body = JSON.parse(lastRequest?.init.body as string) as Record<string, unknown>
    expect(body.usage).toBeUndefined()    // OR-specific: `usage: { include: true }`
    expect(body.reasoning).toBeUndefined() // OR-specific: `reasoning: { effort }`
  })

  test("name derives from baseUrl hostname", () => {
    const provider = new OpenAICompatibleProvider({
      apiKey: "k",
      model: "m",
      baseUrl: "http://localhost:8000/v1",
    })
    expect(provider.name).toBe("openai-compatible(localhost)")
  })

  test("throws ToolArgumentsParseError when tool_call arguments are not JSON", async () => {
    stubFetch({
      id: "chatcmpl-bad",
      object: "chat.completion",
      choices: [
        {
          index: 0,
          message: {
            role: "assistant",
            content: "",
            tool_calls: [
              {
                id: "call_1",
                type: "function",
                function: {
                  name: "extract_fields",
                  arguments: "<think>thinking…</think>{\"name\":\"x\"}",
                },
              },
            ],
          },
          finish_reason: "tool_calls",
        },
      ],
      usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 },
    })
    const provider = new OpenAICompatibleProvider({
      apiKey: "fake",
      model: "test",
      baseUrl: "https://api.example.com/v1",
    })

    let thrown: unknown
    try {
      await provider.complete({
        messages: [{ role: "user", content: "extract" }],
        tools: [{ name: "extract_fields", description: "", inputSchema: {} }],
      })
    } catch (e) {
      thrown = e
    }

    const { ToolArgumentsParseError } = await import("../../src/providers/errors.ts")
    expect(thrown).toBeInstanceOf(ToolArgumentsParseError)
    expect((thrown as InstanceType<typeof ToolArgumentsParseError>).rawArguments)
      .toBe("<think>thinking…</think>{\"name\":\"x\"}")
  })
})

describe("OpenAICompatibleProvider error classification", () => {
  test("401 throws ProviderAuthError (non-retryable)", async () => {
    stubFetch({ error: "invalid key" }, 401)
    const provider = new OpenAICompatibleProvider({
      apiKey: "bad",
      model: "m",
      baseUrl: "https://api.example.com/v1",
    })

    let thrown: unknown
    try {
      await provider.complete({ messages: [{ role: "user", content: "hi" }] })
    } catch (e) {
      thrown = e
    }

    expect(thrown).toBeInstanceOf(ProviderAuthError)
    expect(isProviderError(thrown)).toBe(true)
    expect((thrown as ProviderAuthError).retryable).toBe(false)
  })

  test("403 throws ProviderAuthError", async () => {
    stubFetch({ error: "forbidden" }, 403)
    const provider = new OpenAICompatibleProvider({
      apiKey: "k",
      model: "m",
      baseUrl: "https://api.example.com/v1",
    })

    let thrown: unknown
    try {
      await provider.complete({ messages: [{ role: "user", content: "hi" }] })
    } catch (e) {
      thrown = e
    }

    expect(thrown).toBeInstanceOf(ProviderAuthError)
  })

  test("400 throws ProviderHttpError with status", async () => {
    stubFetch({ error: "bad request" }, 400)
    const provider = new OpenAICompatibleProvider({
      apiKey: "k",
      model: "m",
      baseUrl: "https://api.example.com/v1",
    })

    let thrown: unknown
    try {
      await provider.complete({ messages: [{ role: "user", content: "hi" }] })
    } catch (e) {
      thrown = e
    }

    expect(thrown).toBeInstanceOf(ProviderHttpError)
    expect((thrown as ProviderHttpError).status).toBe(400)
    expect((thrown as ProviderHttpError).retryable).toBe(false)
  })

  test("non-retryable fetch throw rewraps as ProviderNetworkError", async () => {
    // Error message doesn't match network keywords, so the retry loop bails
    // immediately instead of sleeping 3x. We still expect the final throw
    // to be a ProviderNetworkError (that's the class for all `fetch`
    // rejections, retryable or not).
    stubFetchThrow(new Error("simulated test fetch failure (no retry)"))
    const provider = new OpenAICompatibleProvider({
      apiKey: "k",
      model: "m",
      baseUrl: "https://api.example.com/v1",
    })

    let thrown: unknown
    try {
      await provider.complete({ messages: [{ role: "user", content: "hi" }] })
    } catch (e) {
      thrown = e
    }

    expect(thrown).toBeInstanceOf(ProviderNetworkError)
    expect((thrown as ProviderNetworkError).retryable).toBe(true)
  })
})
