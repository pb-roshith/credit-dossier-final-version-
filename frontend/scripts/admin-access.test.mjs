import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import test from "node:test";
import { createRequestGateway } from "./request-gateway.mjs";

test("admin pages require a verified administrator session before forwarding", async () => {
  let rendered = 0;
  const app = createServer((req, res) => {
    if (req.url === "/api/auth/me") {
      res.setHeader("Content-Type", "application/json");
      const cookie = req.headers.cookie;
      if (cookie === "session=admin") res.end('{"role":"admin"}');
      else if (cookie === "session=user") res.end('{"role":"credit_analyst"}');
      else if (cookie === "session=unavailable") { res.writeHead(500); res.end("private error"); }
      else { res.writeHead(401); res.end("expired"); }
      return;
    }
    rendered++;
    res.setHeader("Server", "private-framework/1.0");
    res.setHeader("X-Powered-By", "private-library/2.0");
    res.end('admin page<script src="/assets/react-library.js"></script>');
  });
  app.listen(0, "127.0.0.1");
  await once(app, "listening");
  const gateway = createRequestGateway(app.address().port);
  gateway.listen(0, "127.0.0.1");
  await once(gateway, "listening");
  const origin = `http://127.0.0.1:${gateway.address().port}`;
  try {
    for (const path of ["/admin", "/admin/", "/admin/users", "/%61dmin/", "/admin%2f", "/%2561dmin/"]) {
      for (const [cookie, expected] of [[null, 401], ["session=expired", 401], ["session=user", 403], ["session=unavailable", 503]]) {
        const response = await fetch(origin + path, { headers: cookie ? { Cookie: cookie } : {} });
        assert.equal(response.status, expected, `${path}: ${cookie}`);
        assert.equal(response.headers.get("cache-control"), "no-store");
        assert.doesNotMatch(await response.text(), /admin page|private error|<script|react-library/);
        assert.equal(response.headers.get("server"), null);
        assert.equal(response.headers.get("x-powered-by"), null);
      }
    }
    assert.equal(rendered, 0);
    const allowed = await fetch(origin + "/admin/", { headers: { Cookie: "session=admin" } });
    assert.equal(allowed.status, 200);
    assert.match(await allowed.text(), /admin page/);
    assert.equal(allowed.headers.get("server"), null);
    assert.equal(allowed.headers.get("x-powered-by"), null);
    assert.equal(rendered, 1);
    for (const path of ["/dashboard", "/dashboard/", "/dashboard/deals", "/%64ashboard/", "/dashboard%2f", "/%2564ashboard/"]) {
      const before = rendered;
      for (const [cookie, expected] of [[null, 401], ["session=expired", 401], ["session=unavailable", 503]]) {
        const response = await fetch(origin + path, { headers: cookie ? { Cookie: cookie } : {} });
        assert.equal(response.status, expected, `${path}: ${cookie}`);
        assert.equal(response.headers.get("cache-control"), "no-store");
        assert.doesNotMatch(await response.text(), /admin page|private error/);
      }
      assert.equal(rendered, before);
      for (const cookie of ["session=user", "session=admin"]) {
        const response = await fetch(origin + path, { headers: { Cookie: cookie } });
        assert.equal(response.status, 200);
        assert.equal(response.headers.get("cache-control"), "no-store");
        await response.text();
      }
    }
    assert.equal((await fetch(origin + "/login")).status, 200);
  } finally {
    gateway.closeAllConnections();
    app.closeAllConnections();
    await Promise.all([new Promise((resolve) => gateway.close(resolve)), new Promise((resolve) => app.close(resolve))]);
  }
});
