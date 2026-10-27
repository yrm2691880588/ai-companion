import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "node_modules", "tests/*.mjs", "tmp"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
      // set-state-in-effect：对「effect 里先 await 再 setState」的加载模式误报较多，
      // 项目统一采用「进入页面 → 异步拉数据 → setState」的写法，故降级为 warn。
      // 真正的同步 setState 反模式仍会在 review 与页面验收中暴露。
      "react-hooks/set-state-in-effect": "warn",
      // 不允许用 any 绕过类型
      "@typescript-eslint/no-explicit-any": "error",
      // 允许以 _ 开头的未使用参数（约定俗成表示“故意不用”）
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // 生产代码不允许留调试输出
      "no-console": ["error", { allow: ["warn", "error"] }],
      "no-debugger": "error",
      eqeqeq: ["error", "smart"],
      "prefer-const": "error",
    },
  },
);
