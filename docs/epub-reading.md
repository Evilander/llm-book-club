# EPUB text in the reader

New EPUB uploads preserve paragraphs, source headings, emphasis, quotations, list labels, explicit verse breaks, and preformatted spacing. Chapter headings appear where the author placed them. Continuing pages keep the running title above the paper without repeating a chapter opening.

The reader uses the book's spine order and plain text with typed formatting ranges. It does not execute EPUB HTML or load its stylesheets, scripts, or linked assets. Images, tables, nested list indentation, fixed layouts, and publisher-specific typography are not reproduced. Page length still uses a viewport-dependent character estimate; a verse-heavy page can be taller than prose.

Bionic text can be combined with author emphasis and passage highlights. It leaves code and preformatted blocks alone. Its setting and intensity are saved with the other reading preferences.

## Books already in the library

On the next page request, the API tries to recover formatting from the original EPUB in the upload storage directory or configured books directory. It reproduces the old extraction exactly and verifies it against the stored chunks. Only matching block and mark spans are used. This updates derived book metadata; it does not re-ingest the book or change its text, chunk IDs, citations, conversations, memory, edition hash, or saved coordinates.

Successful formatting is stored in `books.metadata_json.reading_layout` with a format version and reading edition hash. A page request reuses it only when that hash and the ranges validate. The original EPUB is no longer needed after successful recovery. Missing, changed, unsupported, or invalid originals fall back to the existing text; uncovered ranges remain visible as plain paragraphs.

Recovery reads at most 64 MiB of source data, rejects archives with more than 10,000 entries or 256 MiB of expanded content, and confines source paths to configured roots. Failed parses use a process-local cache of at most 32 entries for five minutes, keyed by book ID, edition, resolved path, file size, and modification time. A changed source or edition bypasses the failure entry. This saves repeated parsing without retaining the original prose in that cache.

## API contract

`GET /v1/books/{id}/reader` adds `blocks` alongside its existing `text`, `chunks`, and page coordinates. Each block has `kind`, `char_start`, `char_end`, `marks`, and `continued`; headings can include `level`, and list items can include `list_label`. Marks use the same half-open Unicode code-point coordinates as blocks and the assembled reading edition. Ranges are clipped to the returned page. A continued list item omits its label.

Block kinds are `paragraph`, `heading`, `quote`, `list_item`, and `preformatted`. Mark kinds are `emphasis`, `strong`, `code`, `superscript`, `subscript`, `line_break`, and `join`. The last hides only a verified newline inserted between adjacent inline text fragments by legacy extraction; the canonical text and its offsets remain unchanged.

See [reading boundaries](grounding-and-reading-boundaries.md) for citation and edition invariants. The [EPUB specification](https://www.w3.org/TR/epub-33/) describes the source spine and content documents.
