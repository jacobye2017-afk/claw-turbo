/**
 * YAML config loader with file-watch hot reload.
 */

import { readFileSync, watchFile, unwatchFile, existsSync } from "node:fs";
import { resolve } from "node:path";
import { homedir } from "node:os";

// Use dynamic import for js-yaml to handle ESM
let yaml: any;

async function loadYaml(): Promise<any> {
  if (!yaml) {
    yaml = (await import("js-yaml")).default;
  }
  return yaml;
}

export interface RoutesFileData {
  routes: Array<{
    name: string;
    description?: string;
    patterns: string[];
    command: string;
    response_template?: string;
  }>;
}

const DEFAULT_ROUTES_PATH = resolve(
  homedir(),
  ".openclaw",
  "claw-turbo",
  "routes.yaml"
);

/**
 * Resolve the routes.yaml path.
 */
export function resolveRoutesPath(configPath?: string): string {
  if (configPath) return resolve(configPath);
  return DEFAULT_ROUTES_PATH;
}

/**
 * Load and parse routes.yaml.
 */
export async function loadRoutesFile(path: string): Promise<RoutesFileData> {
  if (!existsSync(path)) {
    throw new Error(`Routes file not found: ${path}`);
  }
  const content = readFileSync(path, "utf-8");
  const jsYaml = await loadYaml();
  const data = jsYaml.load(content) as RoutesFileData;
  if (!data?.routes || !Array.isArray(data.routes)) {
    throw new Error(`Invalid routes.yaml: missing 'routes' array`);
  }
  return data;
}

/**
 * Watch a file for changes and call the callback on modification.
 */
export function watchRoutesFile(
  path: string,
  onChange: () => void
): () => void {
  watchFile(path, { interval: 1000 }, () => {
    onChange();
  });
  return () => unwatchFile(path);
}
