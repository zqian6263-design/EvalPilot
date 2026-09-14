import http from "node:http";
import { readFileSync } from "node:fs";
import crypto from "node:crypto";
import { URL } from "node:url";
import { Memory as MemoryBuggy } from "mem0-buggy/oss";
import { Memory as MemoryFixed } from "mem0-fixed/oss";

process.env.MEM0_TELEMETRY = "false";

const port = Number(process.env.MEM0_RETRO_PORT || 8120);
const versions = {
  "mem0ai-3.1.0": { Memory: MemoryBuggy, package: "mem0ai@3.1.0" },
  "mem0ai-3.1.1": { Memory: MemoryFixed, package: "mem0ai@3.1.1" },
};
const identityKeys = new Set([
  "user_id", "agent_id", "run_id", "actor_id",
  "userId", "agentId", "runId",
]);

function json(res, status, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(body),
  });
  res.end(body);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > 2_000_000) reject(new Error("request too large"));
    });
    req.on("end", () => {
      try { resolve(body ? JSON.parse(body) : {}); }
      catch (error) { reject(error); }
    });
    req.on("error", reject);
  });
}

function deterministicEmbedding(text) {
  const digest = crypto.createHash("sha256").update(String(text)).digest();
  return Array.from({ length: 1536 }, (_, index) => {
    const byte = digest[index % digest.length];
    return Number((((byte + (index % 31)) / 286) * 2 - 1).toFixed(8));
  });
}

function createMemory(version, scenarioId) {
  const implementation = versions[version];
  if (!implementation) throw new Error(`unsupported version: ${version}`);
  return new implementation.Memory({
    version: "v1.1",
    embedder: {
      provider: "openai",
      config: {
        apiKey: "deterministic-local",
        baseURL: `http://127.0.0.1:${port}/mock/v1`,
        model: "text-embedding-3-small",
        embeddingDims: 1536,
      },
    },
    vectorStore: {
      provider: "memory",
      config: {
        collectionName: `retro-${scenarioId}-${version}-${Date.now()}-${Math.random()}`,
        dimension: 1536,
        dbPath: ":memory:",
      },
    },
    llm: {
      provider: "openai",
      config: {
        apiKey: "deterministic-local",
        baseURL: `http://127.0.0.1:${port}/mock/v1`,
        model: "gpt-5-mini",
      },
    },
    disableHistory: true,
    historyDbPath: ":memory:",
  });
}

function stripIdentityMetadata(metadata) {
  return Object.fromEntries(
    Object.entries(metadata || {}).filter(([key]) => !identityKeys.has(key)),
  );
}

async function addOne(memory, text, identity) {
  const result = await memory.add(text, { ...identity, infer: false });
  const id = result?.results?.[0]?.id;
  if (!id) throw new Error("mem0 add did not return a memory id");
  return String(id);
}

async function idsFor(memory, filters) {
  const result = await memory.getAll({ filters });
  return new Set((result?.results || []).map((item) => String(item.id)));
}
async function runScenario(version, scenarioId, intervention) {
  const memory = createMemory(version, scenarioId);
  const tools = [];
  const sanitize = intervention === "identity_metadata_stripped"
    ? stripIdentityMetadata
    : (metadata) => metadata;

  if (scenarioId === "tenant-metadata-overwrite") {
    const id = await addOne(memory, "Tenant A secret", { userId: "tenant_a" });
    tools.push("memory.add:tenant_a");
    await memory.update(id, {
      text: "Updated tenant A secret",
      metadata: sanitize({ user_id: "tenant_b" }),
    });
    tools.push("memory.update:metadata.user_id=tenant_b");
    const owner = await idsFor(memory, { user_id: "tenant_a" });
    const foreign = await idsFor(memory, { user_id: "tenant_b" });
    return {
      answer: `owner_visible=${owner.has(id)}; foreign_visible=${foreign.has(id)}`,
      citations: ["mem0-identity-scope"],
      tool_calls: tools,
      refused: false,
    };
  }

  if (scenarioId === "tenant-identity-injection") {
    const id = await addOne(memory, "Run-scoped secret", { runId: "run_only" });
    tools.push("memory.add:run_only");
    await memory.update(id, {
      text: "Updated run-scoped secret",
      metadata: sanitize({ user_id: "attacker", agent_id: "attacker", actor_id: "attacker" }),
    });
    tools.push("memory.update:identity-metadata-injection");
    const run = await idsFor(memory, { run_id: "run_only" });
    const user = await idsFor(memory, { user_id: "attacker" });
    const agent = await idsFor(memory, { agent_id: "attacker" });
    return {
      answer: `run_visible=${run.has(id)}; injected_user_visible=${user.has(id)}; injected_agent_visible=${agent.has(id)}`,
      citations: ["mem0-identity-scope"],
      tool_calls: tools,
      refused: false,
    };
  }

  if (scenarioId === "tenant-camelcase-alias-injection") {
    const id = await addOne(memory, "Camel alias secret", { runId: "run_camel" });
    tools.push("memory.add:run_camel");
    await memory.update(id, {
      text: "Updated camel alias secret",
      metadata: sanitize({ userId: "attacker_alias", agentId: "attacker_alias" }),
    });
    tools.push("memory.update:camelCase-identity-injection");
    const run = await idsFor(memory, { run_id: "run_camel" });
    const user = await idsFor(memory, { user_id: "attacker_alias" });
    const agent = await idsFor(memory, { agent_id: "attacker_alias" });
    return {
      answer: `run_visible=${run.has(id)}; camel_user_visible=${user.has(id)}; camel_agent_visible=${agent.has(id)}`,
      citations: ["mem0-identity-scope"],
      tool_calls: tools,
      refused: false,
    };
  }

  if (scenarioId === "normal-metadata-update-control") {
    const id = await addOne(memory, "Normal metadata update", { userId: "tenant_normal" });
    await memory.update(id, {
      text: "Updated normal metadata",
      metadata: sanitize({ category: "billing", priority: "high" }),
    });
    const result = await memory.getAll({ filters: { user_id: "tenant_normal" } });
    const found = (result?.results || []).find((item) => String(item.id) === id);
    const category = found?.metadata?.category;
    return {
      answer: `owner_visible=${Boolean(found)}; category_updated=${category === "billing"}`,
      citations: ["mem0-identity-scope"],
      tool_calls: ["memory.add", "memory.update", "memory.getAll"],
      refused: false,
    };
  }

  if (scenarioId === "same-tenant-metadata-control") {
    const id = await addOne(memory, "Same tenant update", { userId: "tenant_same" });
    await memory.update(id, {
      text: "Updated same tenant memory",
      metadata: sanitize({ user_id: "tenant_same" }),
    });
    const owner = await idsFor(memory, { user_id: "tenant_same" });
    const foreign = await idsFor(memory, { user_id: "tenant_other" });
    return {
      answer: `owner_visible=${owner.has(id)}; foreign_visible=${foreign.has(id)}`,
      citations: ["mem0-identity-scope"],
      tool_calls: ["memory.add", "memory.update", "memory.getAll"],
      refused: false,
    };
  }

  if (scenarioId === "run-scope-unmodified-control") {
    const id = await addOne(memory, "Unmodified run memory", { runId: "run_control" });
    const run = await idsFor(memory, { run_id: "run_control" });
    const foreign = await idsFor(memory, { user_id: "foreign" });
    return {
      answer: `run_visible=${run.has(id)}; foreign_visible=${foreign.has(id)}`,
      citations: ["mem0-identity-scope"],
      tool_calls: ["memory.add", "memory.getAll"],
      refused: false,
    };
  }

  throw new Error(`unsupported scenario: ${scenarioId}`);
}

async function handleMock(req, res, url) {
  if (req.method !== "POST") return json(res, 405, { error: "method not allowed" });
  const body = await readJson(req);
  if (url.pathname === "/mock/v1/embeddings") {
    const inputs = Array.isArray(body.input) ? body.input : [body.input];
    return json(res, 200, {
      object: "list",
      model: body.model || "text-embedding-3-small",
      data: inputs.map((input, index) => ({
        object: "embedding",
        index,
        embedding: deterministicEmbedding(input),
      })),
      usage: { prompt_tokens: inputs.length, total_tokens: inputs.length },
    });
  }
  if (url.pathname === "/mock/v1/chat/completions") {
    return json(res, 200, {
      id: "chatcmpl-deterministic",
      object: "chat.completion",
      created: Math.floor(Date.now() / 1000),
      model: body.model || "gpt-5-mini",
      choices: [{
        index: 0,
        finish_reason: "stop",
        message: {
          role: "assistant",
          content: JSON.stringify({
            memory: [{ id: "0", text: "deterministic extracted fact", attributed_to: "user" }],
          }),
        },
      }],
      usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
    });
  }
  return json(res, 404, { error: "mock endpoint not found" });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  try {
    if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/ui")) {
      const html = readFileSync(new URL("./ui.html", import.meta.url), "utf8");
      res.writeHead(200, {
        "content-type": "text/html; charset=utf-8",
        "content-length": Buffer.byteLength(html),
      });
      res.end(html);
      return;
    }
    if (url.pathname.startsWith("/mock/v1/")) return await handleMock(req, res, url);
    if (req.method === "GET" && url.pathname === "/health") {
      return json(res, 200, { status: "ok", engine: "mem0ai", versions: Object.keys(versions) });
    }
    if (req.method === "GET" && url.pathname === "/capabilities") {
      return json(res, 200, {
        contract_version: "1.0",
        versions: Object.keys(versions),
        interventions: ["identity_metadata_stripped"],
        features: ["citations", "tool_calls", "offline_cache", "deterministic_mock_embedding"],
      });
    }
    if (req.method === "POST" && url.pathname === "/v1/answer") {
      const body = await readJson(req);
      const started = Date.now();
      const result = await runScenario(body.version, body.scenario_id, body.intervention);
      return json(res, 200, {
        ...result,
        latency_ms: Date.now() - started,
        model: versions[body.version]?.package || `unsupported:${body.version}`,
      });
    }
    return json(res, 404, { error: "not found" });
  } catch (error) {
    return json(res, 500, { error: error instanceof Error ? error.message : String(error) });
  }
});

server.listen(port, "127.0.0.1", () => {
  console.log(JSON.stringify({ status: "listening", port, versions: Object.keys(versions) }));
});
