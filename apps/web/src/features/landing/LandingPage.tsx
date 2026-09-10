import { Link } from 'react-router-dom'

import { BrandMark } from '@/components/brand/BrandMark'

/**
 * 全屏叙事入口（FRONTEND §5.1 / UIDESIGN §3.3）。
 * 固定深色品牌叙事，不随用户工作区主题切换；Token 深色作用域由
 * tokens.css 的 `.landing` 规则提供。
 */
export function LandingPage() {
  return (
    <div id="landing" className="landing">
      <header className="landing__header">
        <a className="landing__brand" href="#landing" aria-label="EvidSight 首页">
          <BrandMark className="brand-mark" decorative />
          <span>EvidSight</span>
        </a>
        <div className="landing__header-actions">
          <nav className="landing__nav" aria-label="公共导航">
            <a href="#narrative">产品能力</a>
            <a href="#research-method">研究方式</a>
            <a href="#evidence-story">安全与证据</a>
          </nav>
          <Link to="/login" className="landing__login">
            登录
          </Link>
        </div>
      </header>

      <main>
        <section className="landing__hero" aria-labelledby="hero-title">
          <svg
            className="landing__lines"
            viewBox="0 0 1440 860"
            preserveAspectRatio="xMidYMid slice"
            aria-hidden="true"
          >
            <defs>
              <linearGradient id="landing-trace" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0" style={{ stopColor: 'var(--es-moonstone)', stopOpacity: 0 }} />
                <stop
                  offset=".5"
                  style={{ stopColor: 'var(--es-ink-primary)', stopOpacity: 0.72 }}
                />
                <stop
                  offset="1"
                  style={{ stopColor: 'var(--es-spectral-cyan)', stopOpacity: 0.08 }}
                />
              </linearGradient>
            </defs>
            <path
              className="draw-line primary-trace"
              d="M-50 676C210 670 265 420 476 443S731 707 931 512s248-306 573-201"
            />
            <path
              className="draw-line secondary-trace"
              d="M101 890C210 650 361 599 535 635s270 5 372-178 282-244 590-170"
            />
            <path
              className="contour"
              d="M950 93c132 1 251 61 303 160s29 219-58 285-219 67-308 2-109-183-47-286S994 92 950 93Z"
            />
            <path
              className="contour contour-two"
              d="M965 142c98 0 187 45 226 119s21 163-44 211-163 49-229 1-82-136-36-212 115-119 83-119Z"
            />
            <circle className="node node-a" cx="477" cy="443" r="4" />
            <circle className="node node-b" cx="931" cy="512" r="4" />
            <circle className="node node-c" cx="1253" cy="253" r="5" />
          </svg>

          <div className="landing__copy">
            <p className="landing__eyebrow">EVIDENCE-LED INTELLIGENCE · 01</p>
            <h1 id="hero-title" className="landing__hero-title">
              看见线索之间
              <br />
              <span>真正重要的联系</span>
            </h1>
            <p className="landing__lede">
              在内部知识与开放世界之间，追索、交叉验证，直到答案显出轮廓。
            </p>
            <div className="landing__actions">
              <Link to="/login" className="landing__cta">
                <span>进入据见</span>
                <span aria-hidden="true">↗</span>
              </Link>
              <a className="landing__text-link" href="#narrative">
                沿着证据往下看 <span aria-hidden="true">↓</span>
              </a>
            </div>
          </div>
          <div className="landing__coordinate" aria-hidden="true">
            31.2304° N
            <br />
            121.4737° E
          </div>
          <p className="landing__proof">权限在每次取证时复核 · 结论与来源始终相连</p>
        </section>

        <section id="narrative" className="landing__section landing__section--signals">
          <div className="landing__index">02 / SIGNALS</div>
          <div className="landing__statement">
            <p className="landing__eyebrow">散落的信息并不等于知识</p>
            <h2>
              让内部经验与
              <br />
              开放世界彼此印证
            </h2>
          </div>
          <div className="landing__orbit" aria-label="内部知识和公开网络汇聚示意">
            <div className="landing__orbit-label landing__orbit-label--internal">
              内部知识 <small>12 SOURCES</small>
            </div>
            <svg viewBox="0 0 560 300" aria-hidden="true">
              <path d="M-10 91C153 91 163 163 282 163S416 91 570 91" />
              <path d="M-10 236C150 236 174 163 282 163s145 73 288 73" />
              <circle cx="282" cy="163" r="32" />
              <circle className="landing__pulse" cx="282" cy="163" r="5" />
            </svg>
            <div className="landing__orbit-label landing__orbit-label--web">
              公开网络 <small>48 SOURCES</small>
            </div>
          </div>
        </section>

        <section id="research-method" className="landing__section landing__section--method">
          <div className="landing__index">03 / METHOD</div>
          <div className="landing__method">
            <p className="landing__eyebrow">不隐藏过程，也不倾倒思维链</p>
            <h2>研究，在你看得见的地方发生</h2>
          </div>
          <div className="landing__phases" role="list" aria-label="七阶段研究流程">
            <span className="done">规划</span>
            <i aria-hidden="true" />
            <span className="done">检索</span>
            <i aria-hidden="true" />
            <span className="done">获取</span>
            <i aria-hidden="true" />
            <span className="active">重排</span>
            <i aria-hidden="true" />
            <span>综合</span>
            <i aria-hidden="true" />
            <span>证据图谱</span>
            <i aria-hidden="true" />
            <span>生成报告</span>
          </div>
        </section>

        <section id="evidence-story" className="landing__section landing__section--evidence">
          <div className="landing__index">04 / EVIDENCE</div>
          <div className="landing__quote">
            <span className="landing__citation" aria-hidden="true">
              12
            </span>
            <p>
              没有凭据，
              <br />
              不立结论。
            </p>
            <small>每个关键 Claim 都能回到来源、定位与当前权限。</small>
          </div>
          <Link to="/login" className="landing__cta">
            <span>发起研究</span>
            <span aria-hidden="true">↗</span>
          </Link>
        </section>
      </main>

      <footer className="landing__footer">
        <a className="landing__brand landing__brand--small" href="#landing">
          <BrandMark className="brand-mark" decorative />
          <span>EvidSight</span>
        </a>
        <span>从线索，到可信结论。</span>
        <span>© 2026</span>
      </footer>
    </div>
  )
}
