import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from './ui/Button';

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  constructor(props: React.PropsWithChildren) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-zinc-50 px-4 text-center">
          <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-full bg-red-50">
            <AlertTriangle className="h-10 w-10 text-red-500" />
          </div>
          <h1 className="mt-6 text-2xl font-semibold tracking-tight text-zinc-950">Something went wrong</h1>
          <p className="mt-3 max-w-md text-sm text-zinc-500">
            An unexpected error occurred. Please try again or refresh the page.
          </p>
          {this.state.error && (
            <code className="mt-4 max-w-lg rounded-lg bg-zinc-100 px-4 py-2 text-xs text-zinc-600">
              {this.state.error.message}
            </code>
          )}
          <div className="mt-8 flex gap-3">
            <Button variant="outline" onClick={() => window.location.reload()}>
              Refresh page
            </Button>
            <Button variant="primary" onClick={this.handleReset}>
              Try again
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
