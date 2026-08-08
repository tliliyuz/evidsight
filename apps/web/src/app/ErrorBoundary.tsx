import { Component, type ErrorInfo, type PropsWithChildren, type ReactNode } from 'react'

type State = { hasError: boolean }

export class AppErrorBoundary extends Component<PropsWithChildren, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('EvidSight UI 渲染失败', error, info)
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return <main role="alert">页面暂时无法显示，请刷新后重试。</main>
    }
    return this.props.children
  }
}
