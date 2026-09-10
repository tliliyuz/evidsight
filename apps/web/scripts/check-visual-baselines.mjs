import { promises as fs } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDir = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(scriptDir, '..', '..', '..')
const referenceRoot = path.join(repoRoot, 'resource', 'prototype', 'reference', 'evidsight-web')
const manifestPath = path.join(referenceRoot, 'prototype-manifest.json')
const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'))
const errors = []

if (manifest.viewport?.width !== 1280 || manifest.viewport?.height !== 720) {
  errors.push('manifest 视口必须固定为 1280×720')
}

if (!Array.isArray(manifest.pages) || manifest.pages.length !== 20) {
  errors.push('manifest 必须登记 20 个页面')
}

const ids = new Set()
const entries = {
  light: await readReferenceEntry(manifest.lightEntry, '浅色入口'),
  dark: await readReferenceEntry(manifest.darkEntry, '深色入口'),
}

for (const page of manifest.pages ?? []) {
  if (ids.has(page.id)) errors.push(`页面 ID 重复：${page.id}`)
  ids.add(page.id)

  if (!['P0', 'P1'].includes(page.scope)) errors.push(`${page.id}: scope 必须是 P0 或 P1`)
  if (!page.route || !page.source) errors.push(`${page.id}: 缺少 route 或 source`)

  for (const [theme, relativePath] of [
    ['light', page.light],
    ['dark', page.dark],
  ]) {
    const imagePath = path.resolve(referenceRoot, relativePath ?? '')
    try {
      const image = await fs.readFile(imagePath)
      const { width, height } = readPngSize(image)
      if (width !== 1280 || height < 720) {
        errors.push(
          `${page.id}/${theme}: PNG 必须宽 1280px 且高度不低于 720px，实际 ${width}×${height}`,
        )
      }
    } catch (error) {
      errors.push(`${page.id}/${theme}: PNG 不可读取（${error.message}）`)
    }
  }

  for (const [theme, html] of Object.entries(entries)) {
    if (html && !containsSelector(html, page.source)) {
      errors.push(`${page.id}/${theme}: 交互原型缺少 ${page.source}`)
    }
  }
}

if (await exists(path.join(referenceRoot, 'package.json'))) {
  errors.push('跟踪版原型不得包含 package.json 或形成第二前端')
}

const readme = await fs.readFile(path.join(referenceRoot, 'README.md'), 'utf8')
for (const requiredText of [
  '不是第二套生产前端',
  'Chat v1.0 只允许单个知识库',
  '不得覆盖上级规范',
]) {
  if (!readme.includes(requiredText)) errors.push(`README 缺少约束：${requiredText}`)
}

if (errors.length) {
  console.error(`视觉基线检查失败（${errors.length} 项）：`)
  for (const error of errors) console.error(`- ${error}`)
  process.exit(1)
}

console.log('视觉基线检查通过：20 个页面、40 张主题截图、2 个交互入口')

async function readReferenceEntry(entry, label) {
  if (!entry) {
    errors.push(`${label}未登记`)
    return ''
  }
  try {
    return await fs.readFile(path.join(referenceRoot, entry), 'utf8')
  } catch (error) {
    errors.push(`${label}不可读取（${error.message}）`)
    return ''
  }
}

function containsSelector(html, selector) {
  const idMatch = selector.match(/^#([a-z0-9-]+)$/i)
  if (idMatch) return html.includes(`id="${idMatch[1]}"`)

  const attributeMatch = selector.match(/^\[([a-z0-9-]+)='([^']+)'\]$/i)
  if (attributeMatch) return html.includes(`${attributeMatch[1]}="${attributeMatch[2]}"`)

  return false
}

function readPngSize(buffer) {
  const signature = '89504e470d0a1a0a'
  if (buffer.subarray(0, 8).toString('hex') !== signature || buffer.length < 24) {
    throw new Error('不是有效 PNG')
  }
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) }
}

async function exists(target) {
  try {
    await fs.access(target)
    return true
  } catch {
    return false
  }
}
