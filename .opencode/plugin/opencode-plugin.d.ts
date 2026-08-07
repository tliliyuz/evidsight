// 本地最小类型声明：opencode plugin API（仅覆盖本插件用到的部分）。
// opencode 运行时自带 @opencode-ai/plugin 类型；此文件仅供 IDE 静态检查，避免根目录引入 node 依赖。

interface ShellOutput {
  stdout: string
  stderr: string
  exitCode: number
}

interface BunShellPromise extends Promise<ShellOutput> {
  quiet(): BunShellPromise
  nothrow(): BunShellPromise
}

interface BunShell {
  (strings: TemplateStringsArray, ...expressions: unknown[]): BunShellPromise
}

type ToolExecuteAfterInput = {
  tool: string
  sessionID: string
  callID: string
  args: any
}

type ToolExecuteAfterOutput = {
  title: string
  output: string
  metadata: any
}

type Hooks = {
  "tool.execute.after"?: (
    input: ToolExecuteAfterInput,
    output: ToolExecuteAfterOutput,
  ) => Promise<void>
}

type PluginInput = {
  $: BunShell
  worktree: string
  directory: string
}

type Plugin = (input: PluginInput) => Promise<Hooks>

export type { Plugin }
