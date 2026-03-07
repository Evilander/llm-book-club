"use client";

import { useState, useEffect, useCallback } from "react";
import {
  Book,
  Upload,
  Clock,
  FileText,
  AlertCircle,
  CheckCircle,
  Loader2,
  BookMarked,
  Sparkles,
  FileType,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { API_BASE, formatFileSize, formatReadingTime } from "@/lib/utils";

interface BookData {
  id: string;
  title: string;
  author: string | null;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  total_chars: number | null;
  ingest_status: string;
  ingest_error: string | null;
  created_at: string;
}

interface BookTableProps {
  onSelectBook: (bookId: string) => void;
}

// Generate a deterministic gradient based on book title
function getBookGradient(title: string): string {
  const gradients = [
    "from-orange-500/20 via-pink-500/10 to-purple-500/20",
    "from-blue-500/20 via-cyan-500/10 to-teal-500/20",
    "from-emerald-500/20 via-lime-500/10 to-yellow-500/20",
    "from-purple-500/20 via-fuchsia-500/10 to-rose-500/20",
    "from-amber-500/20 via-orange-500/10 to-red-500/20",
    "from-indigo-500/20 via-blue-500/10 to-cyan-500/20",
  ];
  const hash = title.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return gradients[hash % gradients.length];
}

function getFileIcon(fileType: string) {
  switch (fileType.toLowerCase()) {
    case "pdf":
      return <FileType className="w-5 h-5" />;
    case "epub":
      return <BookMarked className="w-5 h-5" />;
    default:
      return <FileText className="w-5 h-5" />;
  }
}

export function BookTable({ onSelectBook }: BookTableProps) {
  const [books, setBooks] = useState<BookData[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const loadBooks = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/books`);
      const data = await res.json();
      setBooks(data.books || []);
    } catch (e) {
      console.error("Failed to load books:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBooks();
    const interval = setInterval(loadBooks, 5000);
    return () => clearInterval(interval);
  }, [loadBooks]);

  async function handleUpload(file: File) {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API_BASE}/v1/ingest`, {
        method: "POST",
        body: fd,
      });
      if (res.ok) {
        loadBooks();
      }
    } catch (e) {
      console.error("Upload failed:", e);
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (
      file &&
      (file.name.endsWith(".pdf") ||
        file.name.endsWith(".epub") ||
        file.name.endsWith(".txt"))
    ) {
      handleUpload(file);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) {
      handleUpload(file);
    }
  }

  function getStatusBadge(status: string) {
    switch (status) {
      case "completed":
        return (
          <Badge variant="success" className="gap-1">
            <CheckCircle className="w-3 h-3" />
            Ready
          </Badge>
        );
      case "processing":
        return (
          <Badge variant="warning" className="gap-1">
            <Loader2 className="w-3 h-3 animate-spin" />
            Processing
          </Badge>
        );
      case "queued":
        return (
          <Badge variant="secondary" className="gap-1">
            <Clock className="w-3 h-3" />
            Queued
          </Badge>
        );
      case "failed":
        return (
          <Badge variant="error" className="gap-1">
            <AlertCircle className="w-3 h-3" />
            Failed
          </Badge>
        );
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  }

  return (
    <div className="space-y-8">
      {/* Upload zone */}
      <Card
        glass
        className={`relative overflow-hidden transition-all duration-300 ${
          dragOver
            ? "border-primary bg-primary/5 shadow-glow"
            : "border-dashed border-2 hover:border-primary/50"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        {/* Animated background pattern */}
        <div className="absolute inset-0 opacity-30">
          <div className="absolute top-1/4 left-1/4 w-32 h-32 bg-primary/20 rounded-full blur-3xl animate-float" />
          <div
            className="absolute bottom-1/4 right-1/4 w-40 h-40 bg-accent/20 rounded-full blur-3xl animate-float"
            style={{ animationDelay: "1s" }}
          />
        </div>

        <CardContent className="relative py-12 text-center">
          <div
            className={`mx-auto mb-4 w-16 h-16 rounded-2xl flex items-center justify-center transition-all duration-300 ${
              dragOver
                ? "bg-primary text-white scale-110"
                : "bg-secondary text-muted-foreground"
            }`}
          >
            {uploading ? (
              <Loader2 className="w-7 h-7 animate-spin" />
            ) : (
              <Upload className="w-7 h-7" />
            )}
          </div>
          <p className="text-lg font-medium mb-2">
            {uploading ? "Uploading..." : "Drop a book here"}
          </p>
          <p className="text-sm text-muted-foreground mb-5">
            PDF, EPUB, or TXT up to 200MB
          </p>
          <label>
            <input
              type="file"
              accept=".pdf,.epub,.txt"
              className="hidden"
              onChange={handleFileSelect}
              disabled={uploading}
            />
            <Button
              variant="outline"
              disabled={uploading}
              asChild
              className="cursor-pointer"
            >
              <span className="gap-2">
                <Sparkles className="w-4 h-4" />
                {uploading ? "Uploading..." : "Choose file"}
              </span>
            </Button>
          </label>
        </CardContent>
      </Card>

      {/* Book grid */}
      {loading ? (
        <div className="text-center py-16">
          <Loader2 className="w-8 h-8 mx-auto mb-4 animate-spin text-primary" />
          <p className="text-muted-foreground">Loading library...</p>
        </div>
      ) : books.length === 0 ? (
        <div className="text-center py-16">
          <div className="mx-auto mb-6 w-20 h-20 rounded-2xl bg-secondary flex items-center justify-center">
            <Book className="w-10 h-10 text-muted-foreground/50" />
          </div>
          <p className="text-lg font-medium mb-1">Your library is empty</p>
          <p className="text-sm text-muted-foreground">
            Upload a book to get started
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {books.map((book, index) => (
            <Card
              key={book.id}
              className={`group relative overflow-hidden cursor-pointer transition-all duration-300 hover:-translate-y-1 hover:shadow-lg ${
                book.ingest_status === "completed"
                  ? "hover:border-primary/50 hover:shadow-glow"
                  : "opacity-80"
              }`}
              style={{ animationDelay: `${index * 50}ms` }}
              onClick={() =>
                book.ingest_status === "completed" && onSelectBook(book.id)
              }
            >
              {/* Gradient background */}
              <div
                className={`absolute inset-0 bg-gradient-to-br ${getBookGradient(
                  book.title
                )} opacity-50 group-hover:opacity-70 transition-opacity`}
              />

              <CardContent className="relative p-5">
                <div className="flex items-start gap-4">
                  {/* Book icon */}
                  <div className="shrink-0 w-14 h-20 rounded-lg bg-secondary/80 border border-border/50 flex items-center justify-center shadow-inner">
                    {getFileIcon(book.file_type)}
                  </div>

                  {/* Book info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2 mb-1">
                      <h3 className="font-semibold text-base line-clamp-2 group-hover:text-primary transition-colors">
                        {book.title}
                      </h3>
                    </div>

                    {book.author && (
                      <p className="text-sm text-muted-foreground mb-2 line-clamp-1">
                        {book.author}
                      </p>
                    )}

                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground mb-3">
                      <span className="uppercase font-medium px-1.5 py-0.5 rounded bg-secondary/50">
                        {book.file_type}
                      </span>
                      <span>{formatFileSize(book.file_size_bytes)}</span>
                      {book.total_chars && (
                        <>
                          <span className="text-border">•</span>
                          <span>
                            {formatReadingTime(Math.round(book.total_chars / 1000))}
                          </span>
                        </>
                      )}
                    </div>

                    {getStatusBadge(book.ingest_status)}

                    {book.ingest_error && (
                      <p className="text-xs text-red-400 mt-2 line-clamp-2">
                        {book.ingest_error}
                      </p>
                    )}
                  </div>
                </div>

                {/* Hover indicator */}
                {book.ingest_status === "completed" && (
                  <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-primary to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
