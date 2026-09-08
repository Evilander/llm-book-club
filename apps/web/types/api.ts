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
  chunks?: { chunk_id: string; section_id: string; char_start: number; char_end: number }[];
}

export interface BookProgressSummary {
  current_unit_id?: string | null;
  current_unit_title?: string | null;
  resume_section_id?: string | null;
  resume_section_title?: string | null;
  units_completed?: number;
  total_units?: number;
  reading_progress_pct?: number;
  last_read_at?: string | null;
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

export interface IngestedBook {
  id: string;
  title: string;
  author: string | null;
  filename: string;
  file_type: string;
  file_size_bytes: number;
  total_chars: number | null;
  ingest_status: string;
  ingest_error: string | null;
  stage?: string | null;
  stage_started_at?: string | null;
  created_at: string;
  section_count: number;
  session_count: number;
  last_session_at: string | null;
  has_audiobook: boolean;
  reading_progress_pct?: number | null;
  current_unit_title?: string | null;
  units_completed?: number | null;
  total_units?: number | null;
  last_read_at?: string | null;
}

export interface LocalBook {
  path: string;
  filename: string;
  extension: string;
  size_bytes: number;
  title_guess: string;
  parent_folder: string | null;
  already_ingested: boolean;
  book_id: string | null;
}

export interface LocalLibraryResponse {
  books_dir: string;
  total: number;
  books: LocalBook[];
}

export interface LocalFolderEntry {
  name: string;
  path: string;
  book_count: number;
  audiobook_count: number;
  sample_titles: string[];
}

export interface LocalFolderLibraryResponse {
  books_dir: string;
  total_books: number;
  folders: LocalFolderEntry[];
  root_book_count: number;
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
  progress?: BookProgressSummary | null;
}

export interface AuthenticatedUser {
  id: string;
  email: string;
  display_name: string | null;
}

export interface ProviderStatus {
  provider: string;
  label: string;
  configured_auth_mode: string;
  oauth_supported: boolean;
  oauth_ready: boolean;
  connected: boolean;
  account_email?: string | null;
  connect_path?: string | null;
  note: string;
}

export interface AuthStatusPayload {
  authenticated: boolean;
  user: AuthenticatedUser | null;
  providers: ProviderStatus[];
}

export interface BinderyStatusResponse {
  paused: boolean;
  queued: number;
  processing: number;
  failed_recent: number;
}

export interface LibrarySearchResult {
  source: "ingested" | "library";
  title: string;
  author: string | null;
  book_id: string | null;
  path: string | null;
  parent_folder: string | null;
  extension: string | null;
  size_bytes: number | null;
  audiobook_count: number;
  score: number;
}

export interface LibrarySearchResponse {
  query: string;
  total: number;
  ingested_count: number;
  library_count: number;
  results: LibrarySearchResult[];
}

export interface ReaderPageResponse {
  book_id: string;
  title: string;
  author: string | null;
  page: number;
  page_size: number;
  total_pages: number;
  total_chars: number;
  current_section_id: string | null;
  current_section_title: string | null;
  current_section_order: number | null;
  text: string;
  char_start: number;
  char_end: number;
}

export interface ReadingPrefsResponse {
  id: string;
  user_id: string;
  theme: string;
  font_family: string;
  font_size_px: number;
  line_height: number;
  measure_ch: number;
  focus_reading: boolean;
  focus_reading_intensity: number;
  created_at: string;
  updated_at: string;
}

export interface ReadingPrefsUpdate {
  theme?: string;
  font_family?: string;
  font_size_px?: number;
  line_height?: number;
  measure_ch?: number;
  focus_reading?: boolean;
  focus_reading_intensity?: number;
}
