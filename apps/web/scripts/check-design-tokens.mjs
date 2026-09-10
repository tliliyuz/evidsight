import { promises as fs } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const webRoot = path.resolve(scriptDir, '..')
const sourceRoot = path.join(webRoot, 'src')
const tokenFile = path.join(sourceRoot, 'styles', 'tokens.css')
const tailwindFile = path.join(webRoot, 'tailwind.config.ts')

const tokenSource = await fs.readFile(tokenFile, 'utf8')
const declaredTokens = new Set(
  [...tokenSource.matchAll(/(^|\s)(--es-[a-z0-9-]+)\s*:/g)].map((match) => match[2]),
)

const sourceFiles = await collectFiles(sourceRoot, new Set(['.css', '.ts', '.tsx']))
const errors = []
const legacyTokens = [
  'midnight',
  'obsidian',
  'surface',
  'surface-2',
  'porcelain',
  'muted',
  'moon',
  'cyan',
  'line',
  'line-strong',
]

for (const file of sourceFiles) {
  const content = await fs.readFile(file, 'utf8')
  const relative = path.relative(webRoot, file)

  for (const match of content.matchAll(/var\(\s*(--es-[a-z0-9-]+)/g)) {
    if (!declaredTokens.has(match[1])) {
      errors.push(`${relative}: 引用了未登记 Token ${match[1]}`)
    }
  }

  if (file !== tokenFile) {
    for (const match of content.matchAll(/(^|\s)(--es-[a-z0-9-]+)\s*:/g)) {
      errors.push(`${relative}: 不得在 tokens.css 之外声明 ${match[2]}`)
    }

    for (const match of content.matchAll(/#[0-9a-f]{3,8}\b|\b(?:rgb|hsl)a?\(/gi)) {
      errors.push(`${relative}: 发现颜色字面量 ${match[0]}`)
    }

    const legacyPattern = new RegExp(`var\\(\\s*--(?:${legacyTokens.join('|')})(?:[,\\s)])`, 'g')
    if (legacyPattern.test(content)) {
      errors.push(`${relative}: 使用了跟踪版原型旧 Token`)
    }
  }
}

const tailwindSource = await fs.readFile(tailwindFile, 'utf8')
for (const match of tailwindSource.matchAll(/var\(\s*(--es-[a-z0-9-]+)/g)) {
  if (!declaredTokens.has(match[1])) {
    errors.push(`tailwind.config.ts: 映射了未登记 Token ${match[1]}`)
  }
}

if (errors.length) {
  console.error(`Design Token 检查失败（${errors.length} 项）：`)
  for (const error of errors) console.error(`- ${error}`)
  process.exit(1)
}

console.log(
  `Design Token 检查通过：${declaredTokens.size} 个 Token，${sourceFiles.length} 个源码文件`,
)

async function collectFiles(directory, extensions) {
  const result = []
  for (const entry of await fs.readdir(directory, { withFileTypes: true })) {
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) {
      result.push(...(await collectFiles(target, extensions)))
    } else if (extensions.has(path.extname(entry.name))) {
      result.push(target)
    }
  }
  return result
}
