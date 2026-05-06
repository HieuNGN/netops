import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: undefined,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen flex items-center justify-center bg-[#f4f4f4] dark:bg-[#161616] px-4">
          <div className="max-w-md w-full bg-white dark:bg-[#262626] rounded-sm shadow-lg border border-[#e0e0e0] dark:border-[#393939] p-8">
            <div className="flex items-center justify-center w-12 h-12 mx-auto bg-[#fff0f1] dark:bg-[#520408] rounded-sm">
              <AlertTriangle className="h-6 w-6 text-[#da1e28] dark:text-[#ff8389]" />
            </div>
            <h1 className="mt-4 text-xl font-bold text-center text-[#161616] dark:text-white">
              Something went wrong
            </h1>
            <p className="mt-2 text-sm text-center text-[#525252] dark:text-[#a8a8a8]">
              An unexpected error occurred. Please try refreshing the page.
            </p>
            {this.state.error && (
              <pre className="mt-4 p-3 bg-[#e0e0e0] dark:bg-[#161616] rounded-sm text-xs text-[#161616] dark:text-[#a8a8a8] overflow-auto max-h-32">
                {this.state.error.message}
              </pre>
            )}
            <button
              onClick={() => window.location.reload()}
              className="mt-6 w-full flex items-center justify-center space-x-2 px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252] transition-colors"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Refresh Page</span>
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
