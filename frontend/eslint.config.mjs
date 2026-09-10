/**
 * Flat ESLint config (ESLint 9). `strict` in tsconfig.json already bans implicit `any`;
 * `@typescript-eslint/no-explicit-any` bans the explicit kind too, per CLAUDE.md.
 */

import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

export default [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
    },
  },
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
];
