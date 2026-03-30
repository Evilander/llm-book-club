import type { Metadata } from "next";
import Link from "next/link";
import { Inter, Space_Grotesk } from "next/font/google";
import { BookOpen, Sparkles } from "lucide-react";
import { Toaster } from "sonner";
import { ErrorBoundary } from "@/components/error-boundary";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-label",
  display: "swap",
});

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
    <html lang="en" className={`${inter.variable} ${spaceGrotesk.variable}`}>
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Literata:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen antialiased">
        <div className="min-h-screen flex flex-col relative">
          <div className="ambient-bg" />

          <header className="sticky top-0 z-50 glass border-b border-border/50">
            <div className="container mx-auto px-4 py-4">
              <div className="flex items-center justify-between">
                <Link href="/" className="flex items-center gap-3 hover:opacity-90 transition-opacity">
                  <div className="relative">
                    <div className="w-11 h-11 rounded-xl gradient-primary flex items-center justify-center shadow-glow">
                      <BookOpen className="w-5 h-5 text-white" />
                    </div>
                    <div className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-emerald-500 border-2 border-background flex items-center justify-center">
                      <Sparkles className="w-2 h-2 text-white" />
                    </div>
                  </div>
                  <div>
                    <h1 className="text-xl font-bold tracking-tight font-serif">
                      <span className="gradient-text">LLM Book Club</span>
                    </h1>
                    <p className="text-xs text-muted-foreground font-label tracking-wide">
                      Open a book. Hear it think back.
                    </p>
                  </div>
                </Link>
              </div>
            </div>
          </header>

          <main className="flex-1">
            <ErrorBoundary>{children}</ErrorBoundary>
          </main>
        </div>

        <Toaster
          theme="dark"
          position="bottom-right"
          toastOptions={{
            style: {
              background: "hsl(20 14% 7%)",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "hsl(30 10% 94%)",
            },
          }}
        />
      </body>
    </html>
  );
}
