import type { Metadata } from "next";
import { LiteraryApp } from "@/components/literary/app";
import "./literary.css";

export const metadata: Metadata = {
  title: "LLM Book Club · Literary Instrument",
  description:
    "Seven-state reading room — dusk, shelf, threshold, spread, lab, after dark, constellation.",
};

export default function LiteraryPage() {
  return <LiteraryApp />;
}
