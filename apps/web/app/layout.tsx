import type { Metadata } from "next";
import Link from "next/link";
import { BookOpen, Settings2 } from "lucide-react";
import {
  Atkinson_Hyperlegible,
  Cormorant_Garamond,
  EB_Garamond,
  JetBrains_Mono,
  Lexend,
} from "next/font/google";
import { Toaster } from "sonner";
import { ErrorBoundary } from "@/components/error-boundary";
import { GlobalSearch } from "@/components/lamplight/global-search";
import "./globals.css";
import "./lite-reader.css";
import "./readagain-shell.css";
import "./after-dark.css";
import "./reading-room.css";

const cormorantGaramond = Cormorant_Garamond({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["400", "500", "600", "700"],
  style: ["normal", "italic"],
  display: "swap",
});

const ebGaramond = EB_Garamond({
  subsets: ["latin"],
  variable: "--font-body",
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500", "600"],
  display: "swap",
});

const lexend = Lexend({
  subsets: ["latin"],
  variable: "--font-lexend",
  weight: ["400", "500", "600"],
  display: "swap",
});

const atkinson = Atkinson_Hyperlegible({
  subsets: ["latin"],
  variable: "--font-atkinson",
  weight: ["400", "700"],
  style: ["normal", "italic"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "ReadAgain — reading, in good company",
  description:
    "A quiet place for your books. Read at your own pace, talk through a passage with an AI companion, or settle into a book club discussion.",
  keywords: [
    "ebook reader",
    "audiobook",
    "book club",
    "ai book discussion",
    "private library",
    "dyslexic reading",
    "lamplight",
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="en"
      className={`${cormorantGaramond.variable} ${ebGaramond.variable} ${jetBrainsMono.variable} ${lexend.variable} ${atkinson.variable}`}
    >
      <body className="min-h-screen font-sans antialiased">
        <a href="#main-content" className="skip-link">Skip to content</a>
        <div className="min-h-screen flex flex-col relative">
          <header className="readagain-topnav">
            <div className="readagain-topnav-inner">
              <Link href="/" className="readagain-topnav-brand" aria-label="ReadAgain home">
                <BookOpen size={23} strokeWidth={1.4} aria-hidden="true" />
                <span className="quiet-wordmark">ReadAgain<span>.</span></span>
              </Link>
              <nav className="readagain-topnav-links" aria-label="Primary">
                <GlobalSearch />
                <Link href="/#library" className="readagain-topnav-link">My library</Link>
                <Link href="/settings" className="readagain-topnav-link" aria-label="Settings"><Settings2 size={18} strokeWidth={1.5} /></Link>
              </nav>
            </div>
          </header>

          <main id="main-content" className="flex-1" tabIndex={-1}>
            <ErrorBoundary>{children}</ErrorBoundary>
          </main>
        </div>

        <Toaster
          theme="light"
          position="bottom-right"
          toastOptions={{
            style: {
              background: "#fffdf8",
              border: "1px solid #deddd2",
              color: "#303b32",
            },
          }}
        />
      </body>
    </html>
  );
}
