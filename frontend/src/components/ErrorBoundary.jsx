import { Component } from 'react'

// Keeps one broken view from blanking the whole app.
export default class ErrorBoundary extends Component {
  state = { error: null }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('Render error:', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="m-6 rounded-card border border-signal/40 bg-signal-pale p-6 text-sm text-signal">
          <p className="font-semibold">Something went wrong displaying this view.</p>
          <p className="mt-1 font-mono text-xs">{String(this.state.error.message || this.state.error)}</p>
          <button type="button" className="mt-4 rounded-full bg-ink px-4 py-1.5 text-on-ink" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
