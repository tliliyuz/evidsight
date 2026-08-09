import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { LandingPage } from '@/features/landing/LandingPage'

describe('入口页（固定深色品牌叙事，FRONTEND §5.1）', () => {
  it('Hero 使用原型主标题而不是超大 EvidSight 字标', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { level: 1, name: /看见线索之间/ })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 1, name: 'EvidSight' })).not.toBeInTheDocument()
  })

  it('恢复品牌 Mark、公共导航与描边登录入口', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )

    expect(screen.getByLabelText('EvidSight 首页')).toBeInTheDocument()

    const nav = screen.getByRole('navigation', { name: '公共导航' })
    expect(within(nav).getByRole('link', { name: '产品能力' })).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: '研究方式' })).toBeInTheDocument()
    expect(within(nav).getByRole('link', { name: '安全与证据' })).toBeInTheDocument()

    const login = screen.getByRole('link', { name: '登录' })
    expect(login).toHaveAttribute('href', '/login')
  })

  it('恢复「进入据见」与「沿着证据往下看」两个层级明确的动作', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )

    expect(screen.getByRole('link', { name: /进入据见/ })).toHaveAttribute('href', '/login')
    expect(screen.getByRole('link', { name: /沿着证据往下看/ })).toHaveAttribute(
      'href',
      '#narrative',
    )
  })

  it('补齐四段纵向叙事：Hero、信息汇聚、研究过程、证据安全', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: /让内部经验/ })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /研究，在你看得见的地方发生/ })).toBeInTheDocument()
    expect(screen.getByText(/没有凭据/)).toBeInTheDocument()
  })

  it('恢复七阶段流程视觉且不展示隐藏推理内容', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )

    const line = screen.getByLabelText('七阶段研究流程')
    for (const phase of ['规划', '检索', '获取', '重排', '综合', '证据图谱', '生成报告']) {
      expect(within(line).getByText(phase)).toBeInTheDocument()
    }
    // 只展示公开阶段名，不展示模型隐藏推理内容
    expect(screen.queryByText(/隐藏推理|内部推理|思考过程|分析轨迹/i)).not.toBeInTheDocument()
  })

  it('锚点导航可被键盘触发并定位到对应叙事区块', () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    )

    const nav = screen.getByRole('navigation', { name: '公共导航' })
    const methodLink = within(nav).getByRole('link', { name: '研究方式' })
    expect(methodLink).toHaveAttribute('href', '#research-method')
    expect(document.querySelector('#research-method')).not.toBeNull()
  })
})
