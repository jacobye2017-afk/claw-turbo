/**
 * Bash command executor — runs matched route commands via child_process.
 */

import { execSync } from "node:child_process";

export interface ExecResult {
  success: boolean;
  returnCode: number;
  stdout: string;
  stderr: string;
  command: string;
}

/**
 * Execute a bash command synchronously.
 */
export function executeCommand(
  command: string,
  timeoutMs: number = 300_000
): ExecResult {
  try {
    const stdout = execSync(command, {
      shell: "/bin/bash",
      timeout: timeoutMs,
      encoding: "utf-8",
      maxBuffer: 10 * 1024 * 1024, // 10MB
    });
    return {
      success: true,
      returnCode: 0,
      stdout: stdout ?? "",
      stderr: "",
      command,
    };
  } catch (err: any) {
    return {
      success: false,
      returnCode: err.status ?? -1,
      stdout: err.stdout ?? "",
      stderr: err.stderr ?? err.message ?? "Unknown error",
      command,
    };
  }
}
