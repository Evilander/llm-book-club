"use client";

/**
 * BulkQueueDialog — lamplight-styled confirm sheet for the
 * "stage the whole shelf" action.
 *
 * Shown when the user clicks the bulk-queue brass button in the folder
 * view. Presents three preset sizes (50 / 200 / 500-or-folder-cap), a
 * typographic time + rough cost estimate per choice, and a single brass
 * confirm CTA. Wires the `/v1/library/local/ingest_folder` endpoint and
 * returns the queued count to the parent so the bindery floor can pick
 * up the wave.
 *
 * Cost estimate is intentionally rough — meant to read like a binder's
 * quote, not a billing total.
 */

import { useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";

interface BulkQueueDialogProps {
  open: boolean;
  folderName: string;
  totalInFolder: number;
  alreadyIngestedCount?: number;
  onCancel: () => void;
  onConfirm: (limit: number) => Promise<void> | void;
}

// Hard cap matches the backend's per-request limit on ingest_folder.
const ABSOLUTE_MAX = 500;

// Rough estimates we use for typographic copy. These are intentional
// craft language, not precise telemetry — the goal is for the user to
// orient before they commit, not to bill them.
const SECONDS_PER_VOLUME = 70; // observed average on the Opus tier
const EMBED_COST_PER_VOLUME_USD = 0.013; // text-embedding-3-large rough avg

interface Preset {
  id: string;
  label: string;
  size: number; // capped at min(size, totalAvailable)
  hint: string;
}

function formatMinutes(seconds: number): string {
  if (seconds < 60) return "under a minute";
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `${mins} min`;
  const hours = Math.round((mins / 60) * 10) / 10;
  return hours === Math.floor(hours) ? `${hours} h` : `${hours} h`;
}

function formatCost(usd: number): string {
  if (usd < 0.5) return `under $0.50 in embeddings`;
  if (usd < 5) return `~$${usd.toFixed(2)} in embeddings`;
  return `~$${Math.round(usd)} in embeddings`;
}

export function BulkQueueDialog({
  open,
  folderName,
  totalInFolder,
  alreadyIngestedCount = 0,
  onCancel,
  onConfirm,
}: BulkQueueDialogProps) {
  const available = Math.max(0, totalInFolder - alreadyIngestedCount);
  const presets: Preset[] = useMemo(() => {
    const sizes = [50, 200, Math.min(ABSOLUTE_MAX, available)];
    const labels = ["The first fifty", "The first two hundred", "All that fits tonight"];
    const hints = [
      "A test run. See how the bindery handles your paper.",
      "A serious sitting. The press will work into the evening.",
      `Up to ${ABSOLUTE_MAX} volumes a batch. Run it again to keep going.`,
    ];
    return sizes
      .map((size, idx) => ({
        id: ["fifty", "two_hundred", "max"][idx],
        size: Math.min(size, available),
        label: labels[idx],
        hint: hints[idx],
      }))
      .filter((preset, idx, all) => {
        // Drop the third preset if available is already <=200 (it'd duplicate the second).
        if (idx === 2 && preset.size <= (all[1]?.size ?? 0)) return false;
        return preset.size > 0;
      });
  }, [available]);

  const [selectedId, setSelectedId] = useState<string>(presets[0]?.id ?? "fifty");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setSelectedId(presets[0]?.id ?? "fifty");
      setError(null);
      setSubmitting(false);
    }
  }, [open, presets]);

  if (!open) return null;

  const selected = presets.find((p) => p.id === selectedId) ?? presets[0];
  const seconds = (selected?.size ?? 0) * SECONDS_PER_VOLUME;
  const cost = (selected?.size ?? 0) * EMBED_COST_PER_VOLUME_USD;

  async function handleConfirm() {
    if (!selected || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm(selected.size);
    } catch (err) {
      setError(err instanceof Error ? err.message : "The bindery refused the batch. Try again.");
      setSubmitting(false);
    }
  }

  return (
    <div className="bulk-scrim" role="dialog" aria-modal="true" aria-label="Stage the whole shelf">
      <section className="bulk-dialog">
        <header className="bulk-dialog-head">
          <p className="binding-eyebrow">
            <span aria-hidden="true">§</span>
            &nbsp;&nbsp;a batch for the bindery
          </p>
          <h2 className="bulk-dialog-title">{folderName}</h2>
          <p className="bulk-dialog-stats">
            <strong>{totalInFolder.toLocaleString()}</strong> volumes in this category
            {alreadyIngestedCount > 0 ? (
              <span className="bulk-dialog-already">
                {" · "}
                {alreadyIngestedCount.toLocaleString()} already shelved
              </span>
            ) : null}
          </p>
        </header>

        <div className="binding-rule" aria-hidden="true">
          <span className="binding-rule-line" />
          <span className="binding-rule-orn">❦</span>
          <span className="binding-rule-line" />
        </div>

        <p className="binding-panel-label">choose the size of the sitting</p>

        <ul className="bulk-presets" role="radiogroup" aria-label="batch size">
          {presets.map((preset) => {
            const isActive = preset.id === selected?.id;
            return (
              <li key={preset.id}>
                <button
                  type="button"
                  role="radio"
                  aria-checked={isActive}
                  onClick={() => setSelectedId(preset.id)}
                  className={cn("bulk-preset", isActive && "is-active")}
                >
                  <span className="bulk-preset-size">{preset.size.toLocaleString()}</span>
                  <span className="bulk-preset-label">{preset.label}</span>
                  <span className="bulk-preset-hint">{preset.hint}</span>
                </button>
              </li>
            );
          })}
        </ul>

        {selected ? (
          <p className="bulk-dialog-estimate">
            <span className="bulk-dialog-elapsed-label">at the press tonight</span>
            <span aria-hidden="true" className="binding-clock-divider" />
            <span>≈ {formatMinutes(seconds)} to clear the line</span>
            <span aria-hidden="true" className="binding-clock-divider" />
            <span>{formatCost(cost)}</span>
          </p>
        ) : null}

        {error ? <p className="bulk-dialog-error">{error}</p> : null}

        <footer className="bulk-dialog-foot">
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="bulk-dialog-cancel"
          >
            cancel
          </button>
          <button
            type="button"
            onClick={() => void handleConfirm()}
            disabled={!selected || submitting}
            className="btn bulk-dialog-confirm"
          >
            {submitting ? "Sending to the press…" : `Send ${selected?.size.toLocaleString() ?? "0"} to the press →`}
          </button>
        </footer>
      </section>
    </div>
  );
}
