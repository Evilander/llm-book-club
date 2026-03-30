/**
 * Shared API response types used across frontend components.
 *
 * These interfaces mirror the JSON shapes returned by the FastAPI backend.
 * Keep component-specific props (e.g. DiscussionStageProps) in the component file.
 */

export interface CitationData {
  chunk_id: string;
  text: string;
  char_start?: number | null;
  char_end?: number | null;
  verified?: boolean;
  match_type?: "exact" | "normalized" | "fuzzy" | null;
}

export interface Message {
  id: string;
  role: string;
  content: string;
  citations: CitationData[] | null;
  created_at: string;
}

export interface Section {
  id: string;
  title: string | null;
  section_type: string;
  order_index: number;
  reading_time_min: number | null;
}

export interface SessionPreferences {
  discussion_style?: string | null;
  vibes?: string[];
  voice_profile?: string | null;
  reader_goal?: string | null;
  experience_mode?: "audio" | "text";
  desire_lens?: string | null;
  adult_intensity?: string | null;
  erotic_focus?: string | null;
}

export interface SessionData {
  session_id: string;
  book_id: string;
  mode: string;
  current_phase: string;
  sections: Section[];
  is_active: boolean;
  preferences?: SessionPreferences | null;
}

export interface ExploreSection {
  id: string;
  title: string | null;
  section_type: string;
  order_index: number;
  reading_time_min: number | null;
  page_start: number | null;
  page_end: number | null;
  preview_text: string;
}

export interface ActiveSection extends ExploreSection {
  text: string;
  chunk_count: number;
  source_refs: string[];
}

export interface AudiobookMatch {
  path: string;
  filename: string;
  extension: string;
  size_bytes: number;
  title_guess: string;
  parent_folder: string | null;
  match_score: number | null;
  match_reason: string | null;
}

export interface ExplorePayload {
  book_id?: string;
  title: string;
  author: string | null;
  filename?: string;
  file_type?: string;
  total_chars?: number | null;
  source_path?: string | null;
  sections: ExploreSection[];
  active_section: ActiveSection | null;
  audiobook_matches: AudiobookMatch[];
  has_local_audiobook: boolean;
  audiobooks_dir?: string | null;
}
