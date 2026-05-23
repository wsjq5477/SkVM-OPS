import { test, expect, describe } from "bun:test"
import { ProviderRouteSchema } from "../../src/core/types.ts"

describe("ProviderRouteSchema discovery metadata", () => {
  test("validates a route with discoveredAt and discoveredFrom", () => {
    const ok = ProviderRouteSchema.safeParse({
      match: "gw/glm-5-thinking",
      kind: "anthropic",
      baseUrl: "https://gw.example.com",
      apiKey: "k",
      discoveredAt: "2026-05-19T01:23:45Z",
      discoveredFrom: "gw/*",
    })
    expect(ok.success).toBe(true)
  })

  test("validates a route WITHOUT the discovery metadata (backwards-compat)", () => {
    const ok = ProviderRouteSchema.safeParse({
      match: "gw/*",
      kind: "openai-compatible",
      baseUrl: "https://gw.example.com/v1",
      apiKey: "k",
    })
    expect(ok.success).toBe(true)
  })

  test("rejects malformed discoveredAt", () => {
    const bad = ProviderRouteSchema.safeParse({
      match: "gw/x", kind: "anthropic", apiKey: "k",
      discoveredAt: "not-a-date",
    })
    expect(bad.success).toBe(false)
  })
})
