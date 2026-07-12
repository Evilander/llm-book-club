export type LiteraryState =
  | "dusk"
  | "shelf"
  | "threshold"
  | "spread"
  | "lab"
  | "after-dark"
  | "constellation";

export type CursorMode = "reader" | "finger" | "loupe" | "quill";
export type BookSkin = "footnote" | "noir" | "poetry";
export type ReaderDensity = "novice" | "expert";
export type AgentRole = "sam" | "ellis" | "kit" | "after-dark";

export interface ShelfBook {
  title: string;
  author: string;
  color: string;
  skin: string;
  pages: number;
  pulled: boolean;
  audio: number;
  last: string;
}

export interface ThresholdChoice {
  slice: string;
  style: string;
  goal: string;
  disposition: number;
  adult: boolean;
}

export interface Tweaks {
  skin: BookSkin;
  density: ReaderDensity;
  reduceMotion: boolean;
}
