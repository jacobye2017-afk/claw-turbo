/**
 * claw-turbo core regex routing engine (TypeScript port).
 * Matches user messages against compiled regex patterns and returns
 * the matched route with captured groups.
 */

export interface RouteConfig {
  name: string;
  description?: string;
  patterns: string[];
  command: string;
  response_template?: string;
}

export interface RoutesConfig {
  routes: RouteConfig[];
}

export interface CompiledRoute {
  name: string;
  description: string;
  patterns: RegExp[];
  rawPatterns: string[];
  command: string;
  responseTemplate: string;
}

export interface MatchResult {
  route: CompiledRoute;
  captures: Record<string, string>;
  rawMessage: string;
  matchTimeUs: number;
}

/**
 * Render a template string by replacing {{key}} with values.
 */
export function renderTemplate(
  template: string,
  variables: Record<string, string>
): string {
  return template.replace(/\{\{(\s*\w+\s*)\}\}/g, (match, key) => {
    const trimmed = key.trim();
    return variables[trimmed] ?? match;
  });
}

/**
 * Compile route configs into regex patterns.
 */
export function compileRoutes(configs: RouteConfig[]): CompiledRoute[] {
  return configs.map((cfg) => ({
    name: cfg.name,
    description: cfg.description ?? "",
    patterns: cfg.patterns.map((p) => new RegExp(p, "i")),
    rawPatterns: cfg.patterns,
    command: cfg.command,
    responseTemplate: cfg.response_template ?? "",
  }));
}

/**
 * Match a message against compiled routes.
 * Returns the first match or null.
 */
export function matchMessage(
  routes: CompiledRoute[],
  message: string
): MatchResult | null {
  const start = performance.now();

  for (const route of routes) {
    for (const pattern of route.patterns) {
      const m = pattern.exec(message);
      if (m) {
        const elapsed = (performance.now() - start) * 1000; // microseconds
        const captures: Record<string, string> = {};
        if (m.groups) {
          for (const [key, val] of Object.entries(m.groups)) {
            if (val !== undefined) captures[key] = val;
          }
        }
        return {
          route,
          captures,
          rawMessage: message,
          matchTimeUs: elapsed,
        };
      }
    }
  }

  return null;
}
