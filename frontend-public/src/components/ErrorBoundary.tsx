import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@gene-guidelines/ui";

interface ErrorBoundaryProps {
  readonly children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, message: "" };
  }

  static getDerivedStateFromError(err: Error): ErrorBoundaryState {
    return { hasError: true, message: err.message || "Unknown error" };
  }

  componentDidCatch(err: Error, info: ErrorInfo): void {
    if (import.meta.env.DEV) {
      console.error("Public app error boundary:", err, info.componentStack);
    }
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="page page--narrow" role="alert">
          <h1 className="page__title">Something went wrong</h1>
          <p className="page__lead">
            The page hit an unexpected error. Reload the app or return home. If this keeps
            happening, note the time and what you clicked.
          </p>
          {import.meta.env.DEV ? (
            <pre className="page__lead" style={{ fontSize: "12px", whiteSpace: "pre-wrap" }}>
              {this.state.message}
            </pre>
          ) : null}
          <div className="page__actions">
            <Button type="button" variant="primary" onClick={() => window.location.reload()}>
              Reload
            </Button>
            <Button type="button" variant="ghost" as="a" href="/">
              Home
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
