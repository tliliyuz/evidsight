import { Link } from 'react-router-dom'

import { BrandMark } from '@/components/brand/BrandMark'

export function LandingPage() {
  return (
    <main className="landing">
      <header className="landing__header">
        <Link to="/" className="landing__brand">
          <BrandMark className="brand-mark" decorative />
          EvidSight
        </Link>
        <nav aria-label="入口导航">
          <a href="#capabilities">可信能力</a>
          <a href="#research">研究方式</a>
          <a href="#evidence">证据安全</a>
          <Link to="/login">登录</Link>
        </nav>
      </header>
      <section className="landing__hero" aria-labelledby="landing-title">
        <p>据见 · Evidence workspace</p>
        <h1 id="landing-title">EvidSight</h1>
        <strong>没有凭据，不立结论。</strong>
        <span>把知识、研究过程与可复核证据放在同一个工作现场。</span>
        <Link to="/login" className="landing__action">
          进入工作区
        </Link>
      </section>
      <section id="capabilities" className="landing__section">
        <h2>结论之前，先看证据</h2>
        <p>每次问答、研究和报告都保留可追溯的来源边界。</p>
      </section>
      <section id="research" className="landing__section">
        <h2>三种研究范围</h2>
        <p>内部知识、公开网络或二者结合，由你明确选择。</p>
      </section>
      <section id="evidence" className="landing__section">
        <h2>权限实时复核</h2>
        <p>引用可以保留，受限原文不会越权展示。</p>
      </section>
    </main>
  )
}
