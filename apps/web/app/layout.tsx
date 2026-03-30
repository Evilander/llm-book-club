import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
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
        <ErrorBoundary>{children}</ErrorBoundary>
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
