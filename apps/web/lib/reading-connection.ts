export class ReadingConnectionRequired extends Error {
  constructor() {
    super("Connect a reading partner to continue. Your place and draft are still here.");
  }
}

export function needsReadingConnection(payload: unknown): boolean {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return false;
  const detail = payload.detail;
  return !!detail && typeof detail === "object" && "code" in detail && detail.code === "reading_connection_required";
}
