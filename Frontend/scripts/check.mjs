import { readdirSync } from "node:fs";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
function check(dir) {
  for (const f of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, f.name);
    if (f.isDirectory()) check(p);
    else if (p.endsWith(".js"))
      execFileSync(process.execPath, ["--check", p], { stdio: "inherit" });
  }
}
check(fileURLToPath(new URL("../src", import.meta.url)));
console.log("Frontend JavaScript syntax checks passed.");
