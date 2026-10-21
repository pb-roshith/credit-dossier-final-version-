import assert from "node:assert/strict";
import { createServer, request } from "node:http";
import { once } from "node:events";
import test from "node:test";
import { createRequestGateway } from "./request-gateway.mjs";

async function fixture(options, run) {
  let forwarded = 0;
  const app = createServer(async (req, res) => {
    forwarded++;
    try { for await (const chunk of req) { /* drain */ } }
    catch { return; }
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ forwardedFor: req.headers["x-forwarded-for"] }));
  });
  app.listen(0, "127.0.0.1");
  await once(app, "listening");
  const gateway = createRequestGateway(app.address().port, options);
  gateway.listen(0, "127.0.0.1");
  await once(gateway, "listening");
  try { await run(gateway.address().port, () => forwarded, gateway); }
  finally {
    gateway.closeAllConnections(); app.closeAllConnections();
    await Promise.all([new Promise(r => gateway.close(r)), new Promise(r => app.close(r))]);
  }
}

test("gateway rate limits before forwarding and overwrites spoofed client identity", async () => {
  await fixture({ requestsPerMinute: 2 }, async (port, count) => {
    const url = `http://127.0.0.1:${port}/api/probe`;
    for (let i = 0; i < 2; i++) {
      const response = await fetch(url, { headers: { "X-Forwarded-For": `1.2.3.${i}` } });
      assert.equal(response.status, 200);
      assert.equal((await response.json()).forwardedFor, "127.0.0.1");
    }
    const blocked = await fetch(url);
    assert.equal(blocked.status, 429);
    assert.equal(blocked.headers.get("retry-after"), "60");
    await blocked.text();
    assert.equal(count(), 2);
  });
});

test("gateway rejects declared and chunked oversized bodies and sets socket bounds", async () => {
  await fixture({}, async (port, count, gateway) => {
    assert.equal(gateway.maxConnections, 128);
    assert.equal(gateway.headersTimeout, 15000);
    assert.equal(gateway.requestTimeout, 60000);
    const declared = await fetch(`http://127.0.0.1:${port}/api/probe`, { method: "POST", body: "a".repeat(2 * 1024 * 1024 + 1) });
    assert.equal(declared.status, 413);
    await declared.text();
    assert.equal(count(), 0);
    const status = await new Promise((resolve, reject) => {
      const req = request({ hostname: "127.0.0.1", port, path: "/api/probe", method: "POST", headers: { "Transfer-Encoding": "chunked" } }, res => {
        res.resume(); res.on("end", () => resolve(res.statusCode));
      });
      req.on("error", reject);
      req.write(Buffer.alloc(1024 * 1024, 97));
      req.end(Buffer.alloc(1024 * 1024 + 1, 97));
    });
    assert.equal(status, 413);
  });
});
