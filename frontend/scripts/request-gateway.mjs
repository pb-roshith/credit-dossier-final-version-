import { createServer, request as httpRequest } from "node:http";

// Check the original target before URL parsers can strip control characters.
export function isSafeRequestTarget(target) {
  if (!target.startsWith("/") || target.startsWith("//")) return false;
  let path = target.split("?", 1)[0];
  if (/[\x00-\x20\x7f\\]/.test(path) || /%(?![0-9a-f]{2})/i.test(path)) return false;
  for (let depth = 0; depth < 8; depth++) {
    if (/[\x00-\x1f\x7f\\]/.test(path)) return false;
    if (!/%[0-9a-f]{2}/i.test(path)) return true;
    path = path.replace(/%([0-9a-f]{2})/gi, (_, hex) => String.fromCharCode(Number.parseInt(hex, 16)));
  }
  return false;
}

export function createRequestGateway(upstreamPort) {
  const server = createServer({ insecureHTTPParser: false }, async (req, res) => {
    res.setHeader("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
    if (!isSafeRequestTarget(req.url ?? "")) {
      res.writeHead(400, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", "Connection": "close", "X-Content-Type-Options": "nosniff" });
      res.end("Bad Request\n");
      return;
    }
    const pathname = new URL(req.url, "http://localhost").pathname;
    let decodedPath = pathname;
    for (let depth = 0; depth < 8 && /%[0-9a-f]{2}/i.test(decodedPath); depth++) {
      decodedPath = decodedPath.replace(/%([0-9a-f]{2})/gi, (_, hex) => String.fromCharCode(Number.parseInt(hex, 16)));
    }
    if (/^\/login\//i.test(decodedPath)) {
      const headers = { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" };
      if (/^\/login\/+$/i.test(decodedPath)) {
        headers.Location = "/login" + new URL(req.url, "http://localhost").search;
        res.writeHead(308, headers);
        res.end("Redirecting to sign in\n");
      } else {
        res.writeHead(404, headers);
        res.end("Not found\n");
      }
      return;
    }
    const isAdminPath = /^\/admin(?:\/|$)/i.test(decodedPath);
    const isProtectedPath = isAdminPath || /^\/dashboard(?:\/|$)/i.test(decodedPath);
    if (isProtectedPath) {
      let status = 401;
      if (req.headers.cookie) {
        try {
          const session = await fetch(`http://127.0.0.1:${upstreamPort}/api/auth/me`, {
            headers: { Cookie: req.headers.cookie },
            redirect: "error",
            signal: AbortSignal.timeout(5000),
          });
          if (session.ok) {
            const user = await session.json();
            const validRole = ["admin", "credit_analyst", "relationship_manager"].includes(user.role);
            status = validRole && (!isAdminPath || user.role === "admin") ? 200 : 403;
          }
          else status = [401, 403].includes(session.status) ? session.status : 503;
        } catch {
          status = 503;
        }
      }
      if (status !== 200) {
        res.writeHead(status, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff" });
        res.end(status === 401 ? "Authentication required\n" : status === 403 ? "Access denied\n" : "Service unavailable\n");
        return;
      }
      res.setHeader("Cache-Control", "no-store");
    }
    const upstream = httpRequest({ hostname: "127.0.0.1", port: upstreamPort, method: req.method, path: req.url, headers: req.headers, insecureHTTPParser: false }, (response) => {
      const responseHeaders = { ...response.headers };
      for (const header of ["server", "x-powered-by", "x-aspnet-version", "x-aspnetmvc-version"]) {
        delete responseHeaders[header];
      }
      res.writeHead(response.statusCode ?? 502, { ...responseHeaders, ...(isProtectedPath ? { "cache-control": "no-store" } : {}), "strict-transport-security": "max-age=31536000; includeSubDomains" });
      response.on("error", () => res.destroy());
      response.pipe(res);
    });
    upstream.on("error", () => {
      if (res.headersSent) res.destroy();
      else {
        res.writeHead(502, { "Content-Type": "text/plain", "Cache-Control": "no-store" });
        res.end("Service unavailable\n");
      }
    });
    req.on("aborted", () => upstream.destroy());
    res.on("close", () => { if (!res.writableFinished) upstream.destroy(); });
    req.pipe(upstream);
  });
  server.on("clientError", (_, socket) => {
    if (socket.writable && !socket.destroyed) socket.end("HTTP/1.1 400 Bad Request\r\nConnection: close\r\nCache-Control: no-store\r\nStrict-Transport-Security: max-age=31536000; includeSubDomains\r\nContent-Length: 0\r\n\r\n");
  });
  return server;
}
