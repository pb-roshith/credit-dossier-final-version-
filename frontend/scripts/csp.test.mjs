import assert from "node:assert/strict";
import test from "node:test";
import handler from "../.output/server/_ssr/ssr.mjs";

test("production SSR uses fresh CSP nonces for every script", async () => {
  const first = await handler.fetch(new Request("http://localhost/"));
  const html = await first.text();
  const policy = first.headers.get("content-security-policy");
  const nonce = policy?.match(/'nonce-([a-f0-9]{64})'/)?.[1];
  assert.equal(first.status, 200);
  assert.equal(first.headers.get("strict-transport-security"), "max-age=31536000; includeSubDomains");
  assert.ok(nonce);
  assert.ok(!policy.split("script-src ")[1].split(";")[0].includes("unsafe-inline"));
  assert.ok(!policy.includes("unsafe-eval"));
  assert.ok(policy.includes("script-src-attr 'none'"));
  assert.ok(policy.includes("'strict-dynamic'"));
  assert.ok(policy.includes("base-uri 'none'"));
  assert.ok(policy.includes("frame-src 'none'"));
  assert.ok(policy.includes("upgrade-insecure-requests"));
  for (const directive of ["style-src", "style-src-elem"]) {
    const value = policy.split(`${directive} `)[1].split(";")[0];
    assert.ok(value.includes(`'nonce-${nonce}'`));
    assert.ok(!value.includes("unsafe-inline"));
  }
  const scripts = [...html.matchAll(/<script\b([^>]*)>/g)];
  assert.ok(scripts.length > 0);
  for (const [, attrs] of scripts) assert.ok(attrs.includes(nonce), attrs);
  const second = await handler.fetch(new Request("http://localhost/"));
  assert.notEqual(second.headers.get("content-security-policy"), policy);
  await second.text();
  assert.equal(first.headers.get("cache-control"), "no-store");
});
