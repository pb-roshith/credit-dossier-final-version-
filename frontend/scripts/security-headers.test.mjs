import assert from "node:assert/strict";
import test from "node:test";
import { spawn } from "node:child_process";
import { createServer } from "node:net";
import { once } from "node:events";
import { fileURLToPath } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

async function freePort() {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const port = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return port;
}

test("production pages, scripts, styles, and missing resources return nosniff with correct MIME types", { timeout: 20000 }, async () => {
  const port = await freePort();
  const app = spawn(process.execPath, [fileURLToPath(new URL("../.output/server/index.mjs", import.meta.url))], {
    windowsHide: true,
    env: { ...process.env, PORT: String(port), NITRO_PORT: String(port), HOST: "127.0.0.1", NITRO_HOST: "127.0.0.1" },
    stdio: "ignore",
  });
  try {
    const base = `http://127.0.0.1:${port}`;
    let page;
    for (let attempt = 0; attempt < 100; attempt++) {
      try { page = await fetch(`${base}/login`); break; } catch { await delay(50); }
    }
    assert.ok(page, "Production server failed to start");
    assert.equal(page.status, 200);
    assert.equal(page.headers.get("x-content-type-options"), "nosniff");
    assert.match(page.headers.get("content-type"), /^text\/html/);
    const html = await page.text();
    const scripts = [...html.matchAll(/(?:src|href)="([^" ]+\.js)"/g)].map(m => m[1]);
    const styles = [...html.matchAll(/href="([^" ]+\.css)"/g)].map(m => m[1]);
    assert.ok(scripts.length, "Expected production JavaScript asset");
    assert.ok(styles.length, "Expected production CSS asset");
    for (const [asset, mime] of [[scripts[0], /^(?:text|application)\/javascript/], [styles[0], /^text\/css/]]) {
      const response = await fetch(new URL(asset, base));
      assert.equal(response.status, 200, asset);
      assert.equal(response.headers.get("x-content-type-options"), "nosniff", asset);
      assert.match(response.headers.get("content-type"), mime, asset);
      await response.arrayBuffer();
    }
    const missing = await fetch(`${base}/assets/nonexistent-security-test.js`);
    assert.equal(missing.status, 404);
    assert.equal(missing.headers.get("x-content-type-options"), "nosniff");
    await missing.text();
  } finally {
    app.kill();
    if (app.exitCode === null) await once(app, "exit");
  }
});
