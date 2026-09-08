---
name: lamplight-nocturne
generated_by: claude-design-mcp
generated_at: 2026-05-11T15:41:54Z
source_system_id: lamplight-nocturne-v1
source_designs:
  - 00590b8880b6
  - feaa9e604817
  - 7335a6153416
  - aa9dc8f67468
spec_version: "0.1"
---

## Everyday reading — current direction

The default experience is a quiet reading room: off-white paper, dark ink, restrained sage accents, and readable book covers. The specification below is retained for the optional After Dark room.

The current implementation lives in `app/reading-room.css`. It loads after the older styles so that the everyday reader, library, book club, and settings share one palette. Book typography uses EB Garamond at 20px / 1.75 by default, with Cormorant Garamond for titles and Atkinson Hyperlegible for controls. Keep controls small and legible; give the book the most space. Offer Bionic text as an optional word-prefix emphasis style with a live preview and adjustable intensity; preserve all text, punctuation, and passage highlights.

Paper choices: Fresh paper (`cream-daylight`), Well-loved (`aged-paper`), Old favorite (`archive-paper`), Bright white (`paper-white`), and Evening (`lamplight-dark`). Grain and edge aging use subtle CSS/SVG textures. Evening keeps an ivory page against a darker desk. Preserve a reader's saved choice.

Pages turn with a short, directional perspective animation; reduced-motion readers get an immediate transition. Page length responds to available space and type size. Save the source position alongside the page size so reflow can preserve the reading location. Let large text scroll when necessary rather than clipping it.

An optional companion sits beside the page on desktop and in a focus-managed drawer on phones. Only exact, verified book passages become highlights. Questions should feel like invitations to pause. Conversations and earlier reader thoughts belong to the book and persist in the backend.

Do not reintroduce invented book notes, decorative volume numbers, wax-seal actions, mandatory introductory rituals, or model setup controls on the library landing page. Keep ordinary actions direct: open a book, turn a page, share a thought.

## Earlier After Dark specification

## Overview

An after-dark private-library system: oxblood rooms, foxed cream paper, brass marginalia, and four agent inks bleeding through every surface.

## Colors

| Token | Value | Role |
|-------|-------|------|
| bg | #2A0E10 | Page background |
| fg | #F2E6D0 | Primary ink |
| accent | #C49A4A | Accent / highlight |
| muted | #9B7B4F | Secondary / muted |
| ellis | #2A0E10 | Ellis |
| ink | #1A1410 | Ink |
| kit | #1B2A3B | Kit |
| lamp | #F7C97A | Lamp |
| paper | #F2E6D0 | Paper |
| pencil | #4A4540 | Pencil |
| sable | #5B1A2A | Sable |
| sam | #A0512A | Sam |

## Typography

| Role | Family |
|------|--------|
| display | "Cormorant Garamond", "Cardo", Georgia, serif |
| body | "EB Garamond", Georgia, serif |
| mono | "JetBrains Mono", ui-monospace, monospace |

### Scale

| Step | Size |
|------|------|
| 0 | 10px |
| 1 | 11px |
| 2 | 13px |
| 3 | 17px |
| 4 | 20px |
| 5 | 26px |
| 6 | 34px |
| 7 | 54px |

## Layout

- **Base unit:** 8px
- **Rhythm:** 1.55

## Elevation & Depth

| Level | Shadow |
|-------|--------|
| low | 0 1px 0 rgba(255,235,200,.06), 0 18px 28px -8px rgba(0,0,0,.55) |
| high | 0 22px 38px -16px rgba(0,0,0,.72), 0 60px 80px -40px rgba(0,0,0,.6), inset 0 0 0 1px rgba(155,123,79,.35) |

## Shapes

| Token | Value |
|-------|-------|
| radius.lg | 3px |
| radius.md | 2px |
| radius.sm | 1px |

## Components

### button-primary

button-primary component extracted by claude-design-mcp.

**HTML**

```html
<button class='btn'>Continue Reading</button>
```

**CSS**

```css
.btn{font-family:"Cormorant Garamond",serif;font-weight:600;font-style:italic;font-size:15px;letter-spacing:.08em;font-variant:small-caps;color:#F2E6D0;background:transparent;border:1.5px solid #C49A4A;border-radius:2px;padding:9px 18px;cursor:pointer;transition:background 180ms cubic-bezier(.22,.61,.36,1),color 180ms}.btn:hover,.btn:focus{background:#C49A4A;color:#1A1410;outline:none}
```

### stamp

stamp component extracted by claude-design-mcp.

**HTML**

```html
<span class='stamp'>Close Reading</span>
```

**CSS**

```css
.stamp{display:inline-block;font-family:"Cormorant Garamond",serif;font-weight:600;letter-spacing:.08em;text-transform:uppercase;font-variant:small-caps;font-size:13px;padding:7px 12px;border:2px solid currentColor;border-radius:2px;color:#2A0E10;background:rgba(42,14,16,.04);transform:rotate(-3deg);cursor:pointer}
```

### card-paper

card-paper component extracted by claude-design-mcp.

**HTML**

```html
<div class='paper'><h2>Chapter VII</h2><p>…</p></div>
```

**CSS**

```css
.paper{background:#F2E6D0;color:#1A1410;padding:34px 44px;border-radius:2px;box-shadow:0 18px 28px -8px rgba(0,0,0,.55),inset 0 0 0 1px rgba(155,123,79,.35);background-image:radial-gradient(circle at 18% 22%,rgba(155,123,79,.18) 0 1px,transparent 2px),radial-gradient(circle at 78% 64%,rgba(155,123,79,.14) 0 1px,transparent 2px),linear-gradient(180deg,#F4E9D2,#EADBBE);background-blend-mode:multiply,multiply,normal}
```

### eyebrow

eyebrow component extracted by claude-design-mcp.

**HTML**

```html
<div class='eyebrow'>After Dark · Vol. II</div>
```

**CSS**

```css
.eyebrow{font-family:"JetBrains Mono",monospace;font-size:10.5px;letter-spacing:.22em;text-transform:uppercase;color:#C49A4A}
```

### rule-ornament

rule-ornament component extracted by claude-design-mcp.

**HTML**

```html
<div class='rule'>❦</div>
```

**CSS**

```css
.rule{display:flex;align-items:center;gap:14px;color:#9B7B4F;font-family:"Cormorant Garamond",serif;font-size:18px;margin:6px 0 24px}.rule::before,.rule::after{content:"";flex:1;height:1px;background:linear-gradient(90deg,transparent,rgba(196,154,74,.45),transparent)}
```

### agent-seal

agent-seal component extracted by claude-design-mcp.

**HTML**

```html
<span class='seal s'>S</span>
```

**CSS**

```css
.seal{display:inline-flex;align-items:center;justify-content:center;width:18px;height:18px;border-radius:50%;font-family:"Cormorant Garamond",serif;font-weight:600;font-size:11px;color:#F2E6D0;box-shadow:inset 0 -2px 3px rgba(0,0,0,.5),inset 0 1px 1px rgba(255,255,255,.18)}.seal.s{background:#A0512A}.seal.e{background:#3a161a}.seal.k{background:#1B2A3B}.seal.v{background:#5B1A2A}
```

### citation-underline

citation-underline component extracted by claude-design-mcp.

**HTML**

```html
<span class='cite cite-sable'>her glass-stemmed lamp</span>
```

**CSS**

```css
.cite{box-shadow:inset 0 -2px 0 #2A0E10;cursor:help}.cite-sable{box-shadow:inset 0 -2px 0 #5B1A2A}.cite-sam{box-shadow:inset 0 -2px 0 #A0512A}.cite-stack{box-shadow:inset 0 -2px 0 #2A0E10,inset 0 -4px 0 -2px #5B1A2A}
```

## Do's and Don'ts

**Do**

- Treat every surface as paper or room — cream stock on oxblood walls, never neutral gray.
- Lamps glow from one corner, not from the center; warmth must have a direction.
- Type is editorial: italic Cormorant for voice, EB Garamond for body, JetBrains Mono only for marginalia and serials.
- Four agents = four inks (sam/ellis/kit/sable). Color carries authorship, never decoration.
- Hairline brass rules, dotted leaders, and foxed paper grain — no rounded cards, no gradient blobs.
- Indices and labels speak archival (folios, serials, Roman numerals, small-caps stamps), never 01/02/03.
