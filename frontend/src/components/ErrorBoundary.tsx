import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = {
  /** Names the failing widget in the fallback, e.g. "Portfolio value". */
  label: string
  /** Smaller fallback, for list items rather than full panels. */
  compact?: boolean
  children: ReactNode
}

type State = { error: Error | null }

/**
 * Contains a render error to one widget.
 *
 * React unmounts the entire tree when a render throws and nothing catches it,
 * so a single panel reading a field off an unexpected API payload takes the
 * whole dashboard to a blank page. Wrapping each widget turns that into one
 * card reporting the problem while its siblings keep rendering.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Keep the component stack in the console; the fallback only shows the message.
    console.error(`[${this.props.label}] render failed`, error, info.componentStack)
  }

  private reset = () => this.setState({ error: null })

  render() {
    const { error } = this.state
    if (!error) return this.props.children

    const { label, compact } = this.props

    if (compact) {
      return (
        <div
          role="alert"
          className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300"
        >
          {label} could not be displayed.
        </div>
      )
    }

    return (
      <section
        role="alert"
        className="rounded-xl border border-rose-300 bg-rose-50 p-4 dark:border-rose-900 dark:bg-rose-950/30"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-rose-700 dark:text-rose-300">
            {label} failed to render
          </h2>
          <button
            type="button"
            onClick={this.reset}
            className="rounded-md border border-rose-400 px-2 py-1 text-[11px] font-semibold text-rose-700 hover:bg-rose-100 dark:border-rose-700 dark:text-rose-300 dark:hover:bg-rose-900/40"
          >
            Try again
          </button>
        </div>
        <p className="mt-2 text-xs text-rose-700/90 dark:text-rose-300/90">
          The rest of the dashboard is unaffected. Details are in the browser console.
        </p>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-[11px] text-rose-800/80 dark:text-rose-200/70">
          {error.message}
        </pre>
      </section>
    )
  }
}
