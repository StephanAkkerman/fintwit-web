import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

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
          className="flex items-center gap-1.5 rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-300"
        >
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {label} could not be displayed.
        </div>
      )
    }

    return (
      <section
        role="alert"
        className="rounded-2xl border border-rose-300 bg-rose-50 p-4 shadow-sm dark:border-rose-900 dark:bg-rose-950/30"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-rose-700 dark:text-rose-300">
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
            {label} isn&apos;t available right now
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
          The rest of the dashboard is unaffected.
        </p>
        <details className="mt-2 text-[11px] text-rose-700/80 dark:text-rose-300/70">
          <summary className="cursor-pointer select-none hover:text-rose-800 dark:hover:text-rose-200">
            Technical details
          </summary>
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-words text-rose-800/80 dark:text-rose-200/70">
            {error.message}
          </pre>
        </details>
      </section>
    )
  }
}
