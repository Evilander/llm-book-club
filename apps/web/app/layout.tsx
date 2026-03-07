import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LLM Book Club",
  description: "Discuss books with AI companions - Facilitator, Close Reader, and more",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
