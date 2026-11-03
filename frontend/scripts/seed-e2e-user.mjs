/**
 * Seeds a throwaway admin for the Playwright suite and prints the credentials
 * as shell exports. Idempotent: reuses the account if it already exists.
 *
 * Seeds through the backend container when the Docker dev stack is up, and
 * otherwise through the repo's own Python (the .venv, or `python` on PATH)
 * against whatever POLARIS_DATABASE_URL the environment points at — so a native
 * stack works with the same `npm run test:e2e`. Skipped automatically when
 * E2E_EMAIL/E2E_PASSWORD are already set.
 */
import { spawnSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

const EMAIL = process.env.E2E_EMAIL || "e2e@polaris.test";

if (process.env.E2E_EMAIL && process.env.E2E_PASSWORD) {
  console.error("E2E credentials already set in the environment — skipping seed.");
  process.exit(0);
}

const password = process.env.E2E_PASSWORD || `E2e-${randomBytes(12).toString("base64url")}`;

const PY = `
import sys
from polaris.db.session import SessionLocal
from polaris.db.models import User
from polaris import auth

email, password = sys.argv[1], sys.argv[2]
db = SessionLocal()
user = db.query(User).filter(User.email == email).first()
if user is None:
    user = User(email=email, username="E2E", role="admin", is_active=True,
                password_hash=auth.hash_password(password))
    db.add(user)
else:
    user.password_hash = auth.hash_password(password)
    user.is_active = True
    user.deleted_at = None
    user.role = "admin"
db.commit()
print("seeded", email)
`;

const compose = [
  "compose",
  "-f",
  "../docker-compose.yml",
  "-f",
  "../docker-compose.dev.yml",
  "exec",
  "-T",
  "backend",
  "python",
  "-c",
  PY,
  EMAIL,
  password,
];

const repoRoot = resolve(process.cwd(), "..");

/** The repo venv's interpreter if it exists, else whatever `python` resolves to. */
function localPython() {
  const candidates =
    process.platform === "win32"
      ? [resolve(repoRoot, ".venv", "Scripts", "python.exe")]
      : [resolve(repoRoot, ".venv", "bin", "python")];
  return candidates.find((c) => existsSync(c)) ?? "python";
}

let result = spawnSync("docker", compose, { encoding: "utf8" });
if (result.status !== 0) {
  // No container to exec into: seed through the local interpreter instead.
  const python = localPython();
  console.error(`Docker dev stack not reachable; seeding with ${python} against POLARIS_DATABASE_URL.`);
  result = spawnSync(python, ["-c", PY, EMAIL, password], {
    encoding: "utf8",
    cwd: repoRoot,
    env: { ...process.env, PYTHONPATH: resolve(repoRoot, "src"), PYTHONUTF8: "1" },
  });
}
if (result.status !== 0) {
  console.error("Failed to seed the E2E user. Start the dev stack, or point POLARIS_DATABASE_URL at a running MySQL.");
  console.error(result.stderr || result.stdout);
  process.exit(1);
}

// Consumed by `npm run test:e2e` via cross-env-style shell export.
process.stdout.write(`${EMAIL}\n${password}\n`);
