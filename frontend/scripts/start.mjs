import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createRequestGateway } from "./request-gateway.mjs";

const port = Number(process.env.PORT ?? 3000);
const upstreamPort = Number(process.env.APP_INTERNAL_PORT ?? 3001);
if (![port, upstreamPort].every((value) => Number.isInteger(value) && value > 0 && value <= 65535) || port === upstreamPort) {
  throw new Error("PORT and APP_INTERNAL_PORT must be distinct valid ports.");
}
const app = spawn(process.execPath, [fileURLToPath(new URL("../.output/server/index.mjs", import.meta.url))], {
  stdio: "inherit",
  env: { ...process.env, PORT: String(upstreamPort), NITRO_PORT: String(upstreamPort), HOST: "127.0.0.1", NITRO_HOST: "127.0.0.1" },
});
const gateway = createRequestGateway(upstreamPort);
gateway.on("error", (error) => { console.error(error); app.kill(); process.exitCode = 1; });
app.on("error", (error) => { console.error(error); gateway.close(); process.exitCode = 1; });
app.on("exit", (code) => { gateway.close(); process.exitCode = code ?? 1; });
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => { gateway.close(); app.kill(signal); });
}
gateway.listen(port, "0.0.0.0", () => console.log(`Request gateway listening on port ${port}`));
