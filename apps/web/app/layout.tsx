import type { Metadata } from "next";
import { ErrorBoundary } from "@/components/error-boundary";
import "./globals.css";

export const metadata: Metadata = {
  title: "LLM Book Club",
  description: "Discuss books with AI companions - Sam, Ellis & Kit",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <ErrorBoundary>{children}</ErrorBoundary>
      </body>
    </html>
  );
}
