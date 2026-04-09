/**
 * claw-turbo OpenClaw Plugin
 *
 * Registers a message interceptor that matches user messages against
 * regex patterns defined in routes.yaml. Matched messages execute
 * skill scripts directly (0ms, 100% accurate), unmatched messages
 * pass through to the LLM normally.
 */

import {
  compileRoutes,
  matchMessage,
  renderTemplate,
  type CompiledRoute,
  type MatchResult,
} from "./router.js";
import { loadRoutesFile, resolveRoutesPath, watchRoutesFile } from "./config.js";
import { executeCommand } from "./executor.js";

interface PluginApi {
  logger: {
    info: (...args: any[]) => void;
    warn: (...args: any[]) => void;
    error: (...args: any[]) => void;
    debug: (...args: any[]) => void;
  };
  config: Record<string, any>;
  pluginConfig: Record<string, any>;
  registerTool: (tool: any, options?: any) => void;
  registerCli: (fn: (opts: { program: any }) => void) => void;
  registerService: (service: any) => void;
  on: (event: string, handler: (...args: any[]) => any) => void;
}

// Plugin state
let compiledRoutes: CompiledRoute[] = [];
let routesPath: string = "";
let unwatchFn: (() => void) | null = null;

async function reloadRoutes(logger: PluginApi["logger"]): Promise<void> {
  try {
    const data = await loadRoutesFile(routesPath);
    compiledRoutes = compileRoutes(data.routes);
    logger.info(
      `[claw-turbo] Loaded ${compiledRoutes.length} routes from ${routesPath}`
    );
  } catch (err: any) {
    logger.error(`[claw-turbo] Failed to load routes: ${err.message}`);
  }
}

function handleMatch(
  match: MatchResult,
  logger: PluginApi["logger"]
): string {
  const templateVars: Record<string, string> = {
    raw_message: match.rawMessage,
    ...match.captures,
  };

  const command = renderTemplate(match.route.command, templateVars);
  logger.info(
    `[claw-turbo] MATCHED [${match.route.name}] in ${match.matchTimeUs.toFixed(1)}us — executing: ${command.slice(0, 100)}`
  );

  const result = executeCommand(command);

  if (result.success) {
    const response = renderTemplate(
      match.route.responseTemplate,
      templateVars
    );
    logger.info(`[claw-turbo] Command succeeded (exit 0)`);
    return response || `Executed ${match.route.name} successfully.`;
  } else {
    logger.warn(
      `[claw-turbo] Command failed (exit ${result.returnCode}): ${result.stderr.slice(0, 200)}`
    );
    return `命令执行失败 (exit ${result.returnCode}): ${result.stderr.slice(0, 200)}`;
  }
}

// ─── Plugin Entry ────────────────────────────────────────────────

export default {
  id: "claw-turbo",
  name: "claw-turbo",
  description:
    "Zero-latency regex skill router — intercepts known commands before LLM inference",

  async register(api: PluginApi) {
    const pluginCfg = api.pluginConfig ?? {};
    const enabled = pluginCfg.enabled !== false;

    if (!enabled) {
      api.logger.info("[claw-turbo] Plugin disabled via config");
      return;
    }

    // Load routes
    routesPath = resolveRoutesPath(pluginCfg.routesPath);
    await reloadRoutes(api.logger);

    // Watch for hot reload
    try {
      unwatchFn = watchRoutesFile(routesPath, () => {
        api.logger.info("[claw-turbo] routes.yaml changed, reloading...");
        reloadRoutes(api.logger);
      });
    } catch {
      api.logger.warn("[claw-turbo] Could not watch routes file for changes");
    }

    // ─── Register Tool ──────────────────────────────────────────
    // Register as an OpenClaw tool so the agent can also explicitly invoke it
    api.registerTool(
      {
        name: "claw_turbo_match",
        description:
          "Check if a user message matches a claw-turbo route and execute it. " +
          "Use this for known command patterns (deploy, restart, print, etc.) " +
          "that can be handled faster than LLM inference.",
        parameters: {
          type: "object",
          properties: {
            message: {
              type: "string",
              description: "The user message to match against routes",
            },
          },
          required: ["message"],
        },
        async execute(args: { message: string }) {
          const match = matchMessage(compiledRoutes, args.message);
          if (!match) {
            return {
              content: [
                {
                  type: "text",
                  text: "No route matched. Let the LLM handle this message normally.",
                },
              ],
            };
          }
          const response = handleMatch(match, api.logger);
          return {
            content: [{ type: "text", text: response }],
          };
        },
      },
      { optional: true }
    );

    // ─── Intercept messages via before_prompt_build ─────────────
    // Inject routing context so the agent knows which commands can be fast-pathed
    api.on("before_prompt_build", async () => {
      if (compiledRoutes.length === 0) return {};

      const routeSummary = compiledRoutes
        .map((r) => `- ${r.name}: ${r.description}`)
        .join("\n");

      return {
        prependSystemContext: [
          "## claw-turbo Fast Routes",
          "The following commands can be executed instantly via the claw_turbo_match tool.",
          "If the user's message matches one of these patterns, use claw_turbo_match instead of trying to execute manually:",
          "",
          routeSummary,
          "",
          'Call: claw_turbo_match({"message": "<user\'s exact message>"})',
        ].join("\n"),
      };
    });

    // ─── Register CLI commands ──────────────────────────────────
    api.registerCli(({ program }) => {
      const turboCmd = program
        .command("turbo")
        .description("claw-turbo route management");

      turboCmd
        .command("routes")
        .description("List all claw-turbo routes")
        .action(async () => {
          await reloadRoutes(api.logger);
          console.log(`\nRoutes from: ${routesPath}\n`);
          compiledRoutes.forEach((route, i) => {
            console.log(`  ${i + 1}. ${route.name}`);
            console.log(`     ${route.description}`);
            route.rawPatterns.forEach((p) => console.log(`     pattern: ${p}`));
            console.log();
          });
        });

      turboCmd
        .command("test <message>")
        .description("Test a message against routes")
        .action(async (message: string) => {
          await reloadRoutes(api.logger);
          const match = matchMessage(compiledRoutes, message);
          if (match) {
            const vars = { raw_message: match.rawMessage, ...match.captures };
            console.log(`\nMATCHED: ${match.route.name}`);
            console.log(`  Captures:  ${JSON.stringify(match.captures)}`);
            console.log(
              `  Command:   ${renderTemplate(match.route.command, vars)}`
            );
            console.log(
              `  Response:  ${renderTemplate(match.route.responseTemplate, vars)}`
            );
            console.log(`  Time:      ${match.matchTimeUs.toFixed(1)}us\n`);
          } else {
            console.log("\nNO MATCH — message would go to LLM.\n");
          }
        });

      turboCmd
        .command("reload")
        .description("Reload routes from disk")
        .action(async () => {
          await reloadRoutes(api.logger);
          console.log(
            `Reloaded ${compiledRoutes.length} routes from ${routesPath}`
          );
        });
    });

    api.logger.info(
      `[claw-turbo] Plugin registered with ${compiledRoutes.length} routes`
    );
  },
};
