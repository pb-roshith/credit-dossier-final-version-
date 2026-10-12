import assert from "node:assert/strict";
import { createServer } from "node:http";
import { once } from "node:events";
import test from "node:test";
import { createRequestGateway } from "./request-gateway.mjs";

test("login directory URLs redirect and nested paths are rejected", async () => {
  let forwarded = 0;
  const app = createServer((req, res) => {
    forwarded++;
    res.end("Sign in");
  });
  app.listen(0, "127.0.0.1");
  await once(app, "listening");
  const gateway = createRequestGateway(app.address().port);
  gateway.listen(0, "127.0.0.1");
  await once(gateway, "listening");
  const origin = `http://127.0.0.1:${gateway.address().port}`;
  try {
    for (const path of ["/login/", "/login//", "/%6cogin/", "/login%2f", "/login/?next=%2Fdashboard"]) {
      const response = await fetch(origin + path, { redirect: "manual" });
      assert.equal(response.status, 308);
      assert.equal(response.headers.get("location"), "/login" + new URL(path, origin).search);
      assert.equal(response.headers.get("cache-control"), "no-store");
      await response.text();
    }
    for (const path of ["/login/files", "/login/index.html", "/login%2ffiles", "/%256cogin/files"]) {
      const response = await fetch(origin + path);
      assert.equal(response.status, 404);
      assert.equal(await response.text(), "Not found\n");
    }
    assert.equal(forwarded, 0);
    const response = await fetch(origin + "/login/");
    assert.equal(response.status, 200);
    assert.equal(await response.text(), "Sign in");
    assert.equal(forwarded, 1);
  } finally {
    gateway.closeAllConnections();
    app.closeAllConnections();
    await Promise.all([new Promise((resolve) => gateway.close(resolve)), new Promise((resolve) => app.close(resolve))]);
  }
});
