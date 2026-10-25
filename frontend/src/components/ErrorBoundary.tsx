import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("页面渲染出错", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="app">
          <main className="main">
            <div className="card" style={{ marginTop: 40 }}>
              <h1>页面出了点问题</h1>
              <p className="muted">不是你的操作问题，刷新一下通常就好。</p>
              <pre className="error-detail">{this.state.error.message}</pre>
              <div className="toolbar">
                <button className="primary" onClick={() => window.location.reload()}>
                  刷新页面
                </button>
                <button className="ghost" onClick={() => (window.location.href = "/")}>
                  回首页
                </button>
              </div>
            </div>
          </main>
        </div>
      );
    }
    return this.props.children;
  }
}
