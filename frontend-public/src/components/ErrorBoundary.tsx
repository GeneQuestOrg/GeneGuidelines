import { Component, type ErrorInfo, type ReactNode } from "react";
import { withTranslation, type WithTranslation } from "react-i18next";
import { Button } from "@gene-guidelines/ui";

interface ErrorBoundaryProps extends WithTranslation {
  readonly children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  message: string;
}

// Class component (React error boundaries have no hooks-based equivalent), so
// i18n is wired via the `withTranslation` HOC rather than `useTranslation`.
class ErrorBoundaryBase extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
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
    const { t } = this.props;
    if (this.state.hasError) {
      return (
        <div className="page page--narrow" role="alert">
          <h1 className="page__title">{t("errorBoundary.title")}</h1>
          <p className="page__lead">{t("errorBoundary.body")}</p>
          {import.meta.env.DEV ? (
            <pre className="page__lead" style={{ fontSize: "12px", whiteSpace: "pre-wrap" }}>
              {this.state.message}
            </pre>
          ) : null}
          <div className="page__actions">
            <Button type="button" variant="primary" onClick={() => window.location.reload()}>
              {t("errorBoundary.reload")}
            </Button>
            <Button type="button" variant="ghost" as="a" href="/">
              {t("errorBoundary.home")}
            </Button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export const ErrorBoundary = withTranslation("common")(ErrorBoundaryBase);
