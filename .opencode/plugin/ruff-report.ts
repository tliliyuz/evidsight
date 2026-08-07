import type { Plugin } from "./opencode-plugin.js"

const PY_RE = /\.py$/

export default (async ({ $, worktree }) => {
  return {
    "tool.execute.after": async (input, output) => {
      const tool = input.tool
      if (tool !== "edit" && tool !== "write") return

      const filePath: unknown = input.args?.file_path
      if (typeof filePath !== "string" || !PY_RE.test(filePath)) return

      const abs = filePath.startsWith("/") ? filePath : `${worktree}/${filePath}`

      const formatDiff = await $`ruff format --check --diff ${abs}`.quiet().nothrow()
      const checkDiff = await $`ruff check --diff ${abs}`.quiet().nothrow()

      if (formatDiff.stdout.trim() === "" && checkDiff.stdout.trim() === "") return

      const summary = [
        "## ruff 报告（未落盘，需要你批准后才会写入）",
        "",
        formatDiff.stdout.trim() !== ""
          ? `### 格式改动（ruff format --check --diff）\n\`\`\`diff\n${formatDiff.stdout}\n\`\`\``
          : "",
        checkDiff.stdout.trim() !== ""
          ? `### lint 修复（ruff check --diff）\n\`\`\`diff\n${checkDiff.stdout}\n\`\`\``
          : "",
        "批准方式：对 `ruff format <file>` / `ruff check --fix <file>` 的执行确认「允许」即可写入。",
      ]
        .filter(Boolean)
        .join("\n\n")

      output.title = `ruff 报告 ${filePath}`
      output.output = summary
      output.metadata = { ruffReport: true }
    },
  }
}) satisfies Plugin
