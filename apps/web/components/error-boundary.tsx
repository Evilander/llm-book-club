"use client";

import { Component, type ReactNode } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  children: ReactNode;
  fallbackMessage?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex items-center justify-center min-h-[400px] p-8">
          <div className="text-center max-w-md space-y-4">
            <div className="w-16 h-16 rounded-full bg-red-500/10 flex items-center justify-center mx-auto">
              <AlertTriangle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-xl font-semibold">Something went wrong</h2>
            <p className="text-sm text-muted-foreground">
              {this.props.fallbackMessage || "An unexpected error occurred. Try refreshing the page."}
            </p>
            {this.state.error && (
              <pre className="text-xs text-left bg-secondary/50 rounded-lg p-3 overflow-auto max-h-32">
                {this.state.error.message}
              </pre>
            )}
            <Button
              variant="outline"
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
            >
              <RotateCcw className="w-4 h-4 mr-2" />
              Reload
            </Button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
