const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { pathToFileURL } = require("node:url");

const pluginRoot = path.resolve(__dirname, "..");
const serverPath = path.join(
  pluginRoot,
  "vendor",
  "premiere-pro-mcp",
  "premiere-mcp.bundle.mjs",
);

if (!process.env.PREMIERE_TEMP_DIR) {
  process.env.PREMIERE_TEMP_DIR = path.join(
    os.tmpdir(),
    "premiere-mcp-bridge",
  );
}

fs.mkdirSync(process.env.PREMIERE_TEMP_DIR, { recursive: true });

if (!fs.existsSync(serverPath)) {
  console.error(`Bundled Premiere MCP server not found: ${serverPath}`);
  process.exit(1);
}

import(pathToFileURL(serverPath).href).catch((error) => {
  console.error("Failed to start the bundled Premiere MCP server:", error);
  process.exit(1);
});
