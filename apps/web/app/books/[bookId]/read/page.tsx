"use client";

import { use } from "react";
import { LiteReader } from "@/components/lite-reader";

export default function ReadBookPage({
  params,
  searchParams,
}: {
  params: Promise<{ bookId: string }>;
  searchParams: Promise<{ page?: string; size?: string }>;
}) {
  const { bookId } = use(params);
  const { page, size } = use(searchParams);
  const initialPage = page ? Math.max(1, parseInt(page, 10) || 1) : undefined;
  return <LiteReader key={bookId} bookId={bookId} initialPage={initialPage} initialPageSize={Math.max(200, Math.min(1800, parseInt(size || "1800", 10) || 1800))} />;
}
