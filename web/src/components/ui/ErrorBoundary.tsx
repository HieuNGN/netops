import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error', error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-[#f4f4f4] dark:bg-[#161616] px-4">
          <div className="max-w-md w-full bg-white dark:bg-[#262626] rounded-sm shadow-sm border border-[#e0e0e0] dark:border-[#393939] p-8 text-center">
            <div className="mx-auto w-12 h-12 bg-[#fff0f1] dark:bg-[#520408] rounded-sm flex items-center justify-center mb-4">
              <AlertTriangle className="h-6 w-6 text-[#da1e28] dark:text-[#ff8389]" />
            </div>
            <h1 className="text-xl font-bold text-[#161616] dark:text-white mb-2">
              Something went wrong
            </h1>
            <p className="text-[#525252] dark:text-[#a8a8a8] mb-6">
              {this.state.error?.message || 'An unexpected error occurred'}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-[#161616] text-white rounded-sm hover:bg-[#525252] transition-colors"
            >
              Reload Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
