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

export function createRequestGateway(upstreamPort, { requestsPerMinute = 600, maxConcurrent = 64, maxClients = 10000 } = {}) {
  const clients = new Map();
  let active = 0;
  const server = createServer({ insecureHTTPParser: false }, async (req, res) => {
    // Default for gateway errors and static/API responses. SSR replaces this
    // header with its per-response nonce policy when upstream headers arrive.
    res.setHeader("Content-Security-Policy", "default-src 'none'; script-src 'none'; script-src-attr 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'");
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
    const reject = (status, message) => {
      res.writeHead(status, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", "Connection": "close", ...([429, 503].includes(status) ? { "Retry-After": "60" } : {}) });
      res.end(message + "\n");
    };
    const now = Date.now();
    for (const [key, value] of clients) {
      if (value.expires > now) break;
      clients.delete(key);
    }
    const peer = req.socket.remoteAddress ?? "unknown";
    if (!clients.has(peer)) {
      if (clients.size >= maxClients) return reject(503, "Server is busy");
      clients.set(peer, { expires: now + 60000, count: 0 });
    }
    if (++clients.get(peer).count > requestsPerMinute) return reject(429, "Too many requests");
    if (active >= maxConcurrent) return reject(503, "Server is busy");
    const bodyLimit = (req.headers["content-type"] ?? "").toLowerCase().startsWith("multipart/form-data") ? 52 * 1024 * 1024 : 2 * 1024 * 1024;
    if (Number(req.headers["content-length"] ?? 0) > bodyLimit) return reject(413, "Request body is too large");
    active++;
    let released = false;
    const release = () => { if (!released) { released = true; active--; } };
    res.once("finish", release);
    res.once("close", release);
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
    const upstream = httpRequest({ hostname: "127.0.0.1", port: upstreamPort, method: req.method, path: req.url, headers: { ...req.headers, "x-forwarded-for": peer }, insecureHTTPParser: false }, (response) => {
      const responseHeaders = { ...response.headers };
      for (const header of ["server", "x-powered-by", "x-aspnet-version", "x-aspnetmvc-version"]) {
        delete responseHeaders[header];
      }
      res.writeHead(response.statusCode ?? 502, { ...responseHeaders, ...(isProtectedPath ? { "cache-control": "no-store" } : {}), "strict-transport-security": "max-age=31536000; includeSubDomains", "x-content-type-options": "nosniff" });
      response.on("error", () => res.destroy());
      response.pipe(res);
    });
    let oversized = false;
    let bytes = 0;
    req.on("data", (chunk) => {
      bytes += chunk.length;
      if (bytes > bodyLimit && !oversized) {
        oversized = true;
        req.unpipe(upstream);
        upstream.destroy();
        if (!res.headersSent) reject(413, "Request body is too large");
        else res.destroy();
      }
    });
    const deadline = setTimeout(() => {
      upstream.destroy();
      if (!res.headersSent) reject(504, "Request timed out");
      else res.destroy();
    }, 300000);
    res.once("close", () => clearTimeout(deadline));
    res.once("finish", () => clearTimeout(deadline));
    upstream.on("error", () => {
      if (oversized || res.writableEnded) return;
      if (res.headersSent) res.destroy();
      else {
        res.writeHead(502, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" });
        res.end("Service unavailable\n");
      }
    });
    req.on("aborted", () => upstream.destroy());
    res.on("close", () => { if (!res.writableFinished) upstream.destroy(); });
    req.pipe(upstream);
  });
  server.headersTimeout = 15000;
  server.requestTimeout = 60000;
  server.keepAliveTimeout = 5000;
  server.maxConnections = 128;
  server.maxRequestsPerSocket = 1000;
  server.on("clientError", (_, socket) => {
    if (socket.writable && !socket.destroyed) socket.end("HTTP/1.1 400 Bad Request\r\nX-Content-Type-Options: nosniff\r\nContent-Type: text/plain; charset=utf-8\r\nConnection: close\r\nCache-Control: no-store\r\nContent-Security-Policy: default-src 'none'; script-src 'none'; script-src-attr 'none'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'none'\r\nStrict-Transport-Security: max-age=31536000; includeSubDomains\r\nContent-Length: 0\r\n\r\n");
  });
  return server;
}
