import assert from "node:assert/strict";
import { createServer } from "node:http";
import { connect } from "node:net";
import { once } from "node:events";
import test from "node:test";
import { createRequestGateway } from "./request-gateway.mjs";

function rawRequest(port, target) {
  return new Promise((resolve, reject) => {
    const socket = connect(port, "127.0.0.1");
    let response = "";
    socket.setTimeout(3000, () => socket.destroy(new Error("Request timed out")));
    socket.on("error", reject);
    socket.on("data", (data) => { response += data.toString(); });
    socket.on("end", () => resolve(response));
    socket.on("connect", () => socket.write(`GET ${target} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n`));
  });
}

test("reject malformed paths before forwarding; preserve valid requests", async () => {
  let forwarded = 0;
  const app = createServer(async (req, res) => {
    forwarded++;
    let body = "";
    for await (const data of req) body += data;
    res.setHeader("Content-Type", "application/json");
    if (req.url === "/nonce-page") {
      res.setHeader("Content-Security-Policy", "script-src 'nonce-test' 'strict-dynamic'");
    }
    res.setHeader("Set-Cookie", ["a=1; HttpOnly", "b=2; HttpOnly"]);
    res.end(JSON.stringify({ url: req.url, method: req.method, cookie: req.headers.cookie, body }));
  });
  app.listen(0, "127.0.0.1");
  await once(app, "listening");
  const gateway = createRequestGateway(app.address().port);
  gateway.listen(0, "127.0.0.1");
  await once(gateway, "listening");
  const port = gateway.address().port;
  try {
    const base = "/assets/triangle-alert-BfPUAUia.js";
    const targets = [base + "\tHTTP/1.1/../../triangle-alert-BfPUAUia.js", base + "%09HTTP/1.1/../../x", base + "%2509HTTP/1.1/../../x", "/assets/%00x.js", "/assets/%1Fx.js", "/assets/%7fx.js", "/assets/%5cx.js", "/assets/%xx.js"];
    for (let code = 0; code <= 31; code++) targets.push(`/assets/x${String.fromCharCode(code)}y.js`);
    targets.push("/assets/x\x7fy.js");
    for (const target of targets) {
      const response = await rawRequest(port, target);
      assert.match(response, /x-content-type-options: nosniff/i);
      assert.match(response, /content-security-policy: default-src 'none'; script-src 'none';/i);
      assert.match(response, /^HTTP\/1\.1 400 /, JSON.stringify(target));
      assert.match(response, /strict-transport-security: max-age=31536000; includeSubDomains/i);
    }
    assert.equal(forwarded, 0);
    for (const target of [base, "/assets/jsx-runtime-D3jfb0Ew.js", "/login", "/api/health", "/assets/caf%C3%A9.js", "/api/search?q=hello%20world"]) {
      const result = await rawRequest(port, target);
      assert.match(result, /x-content-type-options: nosniff/i);
      assert.match(result, /content-security-policy: default-src 'none'; script-src 'none';/i);
      assert.match(result, /^HTTP\/1\.1 200 /);
      assert.match(result, /strict-transport-security: max-age=31536000; includeSubDomains/i);
    }
    const response = await fetch(`http://127.0.0.1:${port}/api/deals`, { method: "POST", headers: { Cookie: "session=test", "Content-Type": "application/json" }, body: '{"name":"Example"}' });
    assert.deepEqual(await response.json(), { url: "/api/deals", method: "POST", cookie: "session=test", body: '{"name":"Example"}' });
    assert.equal(response.headers.getSetCookie().length, 2);
    assert.equal(response.headers.get("x-content-type-options"), "nosniff");
    assert.equal(response.headers.get("content-type"), "application/json");
    const noncePage = await fetch(`http://127.0.0.1:${port}/nonce-page`);
    assert.equal(noncePage.headers.get("content-security-policy"), "script-src 'nonce-test' 'strict-dynamic'");
    await noncePage.text();
    assert.equal(response.headers.get("strict-transport-security"), "max-age=31536000; includeSubDomains");
  } finally {
    gateway.closeAllConnections();
    app.closeAllConnections();
    await Promise.all([new Promise((resolve) => gateway.close(resolve)), new Promise((resolve) => app.close(resolve))]);
  }
});
