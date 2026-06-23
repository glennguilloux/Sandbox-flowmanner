/**
 * Persistent CLI state stored under ~/.flowmanner/.
 *
 * Holds:
 * - JWT bearer (after `flowmanner login`)
 * - Base URL override (for self-hosted / staging)
 * - Default workspace ID (auto-detected after login)
 *
 * Uses `conf` (12-factor config library) so credentials are stored in
 * the OS-conventional config dir with sane permissions (0600 on Unix).
 */
import Conf from "conf";
import { join } from "node:path";
import { homedir } from "node:os";

export const DEFAULT_BASE_URL = "https://flowmanner.com";

// `conf`'s strict schema typing fights us here — we use a permissive
// schema and validate at the boundary. The shape is stable and
// small enough that runtime drift is easy to catch.
//
// `cwd` is overridden so credentials land at ~/.flowmanner/config.json
// rather than conf's default ~/.config/flowmanner-nodejs/...  This
// matches what the docs and our README promise users.
const store = new Conf({
  projectName: "flowmanner",
  cwd: process.env["FLOWMANNER_CONFIG_DIR"] ?? join(homedir(), ".flowmanner"),
  schema: {
    token: { type: "string" },
    baseUrl: { type: "string" },
    email: { type: "string" },
    workspaceId: { type: "string" },
  } as Record<string, { type: string }>,
  clearInvalidConfig: true,
});

export interface Credentials {
  token: string;
  email: string;
  workspaceId?: string;
}

export function saveCredentials(creds: Credentials): void {
  store.set("token", creds.token);
  store.set("email", creds.email);
  if (creds.workspaceId) {
    store.set("workspaceId", creds.workspaceId);
  }
}

export function loadCredentials(): Credentials | null {
  const token = store.get("token");
  const email = store.get("email");
  if (typeof token !== "string" || typeof email !== "string") return null;
  const workspaceId = store.get("workspaceId");
  return typeof workspaceId === "string"
    ? { token, email, workspaceId }
    : { token, email };
}

export function clearCredentials(): void {
  store.delete("token");
  store.delete("email");
  store.delete("workspaceId");
}

export function getBaseUrl(): string {
  const value = store.get("baseUrl");
  return typeof value === "string" && value.length > 0
    ? value
    : DEFAULT_BASE_URL;
}

export function setBaseUrl(url: string): void {
  store.set("baseUrl", url);
}

export function getConfigPath(): string {
  return store.path;
}