// @ts-check
/**
 * ESLint v9 flat-config for @flowmanner/cli.
 *
 * Layered:
 *   1. @eslint/js recommended       — JS correctness baseline
 *   2. typescript-eslint recommended — TS correctness baseline
 *   3. Project rules (below)
 *
 * Every rule that's been relaxed from `error` to `warn` is paired with a
 * `// eslint-disable-next-line` + a tracking comment in the source so the
 * deferral is discoverable in code review. Don't blanket-warn the entire
 * recommended set — that defeats the purpose of having a linter.
 */
import js from "@eslint/js";
import tseslint from "typescript-eslint";
import globals from "globals";

export default [
  {
    ignores: ["dist/**", "node_modules/**", "templates/**"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: "module",
      globals: {
        ...globals.node,
        // Node test runner globals — `test`, `after`, `afterEach`, `before`, `describe`, `it`
        ...globals.nodeBuiltin,
      },
    },
    rules: {
      // Allow underscore-prefixed unused args/vars (CLI flags we don't read).
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // `any` is fine for the thin-client JSON unwrap; promoting to `unknown`
      // everywhere is a v0.2 cleanup.
      "@typescript-eslint/no-explicit-any": "warn",
      // Disable the noisy default that flags every type-only import missing
      // `type` keyword in mixed import statements.
      "@typescript-eslint/consistent-type-imports": "off",
    },
  },
];
