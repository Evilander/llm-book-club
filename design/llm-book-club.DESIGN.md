# LLM Book Club Design System

Last updated: 2026-03-30

## Visual Thesis

Editorial reading salon with cinematic warmth, live voices, and disciplined restraint.

## Product Thesis

Every screen should make the user want to open a slice and stay in the conversation.

## Behavior Thesis

The UI should reduce friction between curiosity, evidence, and the next question.

---

## Typography

| Role | Font | Weight | Usage |
|------|------|--------|-------|
| Headlines | Literata | 600-700 | Page titles, hero text, section headers |
| Body | Inter | 400-500 | UI text, descriptions, message content |
| Labels | Space Grotesk | 500 | Metadata, badges, timestamps, tracking labels |
| Citations | Literata italic | 400 | Quoted passages, marginalia, evidence text |
| Code/IDs | JetBrains Mono | 400 | Chunk IDs, technical metadata |

### Scale

```
text-xs:   0.75rem / 12px  — metadata, timestamps, tracking labels
text-sm:   0.875rem / 14px — body text, descriptions, message content
text-base: 1rem / 16px     — primary UI text
text-lg:   1.125rem / 18px — section headers
text-xl:   1.25rem / 20px  — card titles
text-2xl:  1.5rem / 24px   — page section titles
text-3xl:  1.875rem / 30px — hero subheads
text-4xl:  2.25rem / 36px  — hero headlines (desktop)
text-5xl:  3rem / 48px     — hero headlines (wide desktop)
```

---

## Color Tokens

### Standard Mode

| Token | Value | Usage |
|-------|-------|-------|
| `--background` | stone-950 `#0C0A09` | Page background |
| `--card` | stone-900 `#1C1917` | Card surfaces |
| `--primary` | amber-600 `#D97706` | CTAs, active states, emphasis |
| `--primary-hover` | amber-500 `#F59E0B` | Hover on primary elements |
| `--secondary` | stone-800 `#292524` | Secondary surfaces |
| `--muted` | stone-700 `#44403C` | Muted text, borders |
| `--border` | `rgba(255,255,255,0.08)` | Card borders, dividers |
| `--accent` | amber-500 `#F59E0B` | Gradient accents |

### Agent Colors

| Agent | Color | Token |
|-------|-------|-------|
| Sam (facilitator) | amber-400 `#FBBF24` | `--agent-facilitator` |
| Ellis (close reader) | teal-400 `#2DD4BF` | `--agent-close-reader` |
| Kit (skeptic) | rose-400 `#FB7185` | `--agent-skeptic` |
| After-dark guide | fuchsia-300 `#F0ABFC` | `--agent-after-dark` |
| User | blue-400 `#60A5FA` | `--agent-user` |

### Citation Verification

| State | Color | Indicator |
|-------|-------|-----------|
| Exact match | emerald-400 `#34D399` | Solid dot |
| Normalized | amber-400 `#FBBF24` | Solid dot |
| Fuzzy | amber-300 `#FCD34D` | Open dot |
| Unverified | red-400 `#F87171` | Hollow dot |

### After-Dark Mode Delta

| Token | Standard | After-Dark |
|-------|----------|------------|
| `--background` | stone-950 | stone-950 (deeper shadow) |
| `--primary` | amber-600 | rose-500 `#F43F5E` |
| `--accent` | amber-500 | fuchsia-400 `#E879F9` |
| `--card` | stone-900 | stone-900 + rose-500/5 tint |
| `--border` | white/8 | rose-500/15 |
| gradient-start | amber | rose |
| gradient-end | rose | fuchsia |

---

## Spacing

Base unit: 4px (Tailwind default)

| Context | Spacing |
|---------|---------|
| Card padding | `p-4` to `p-6` |
| Section gap | `space-y-8` to `space-y-10` |
| Grid gap | `gap-3` to `gap-4` |
| Inline gaps | `gap-2` |
| Header padding | `px-4 py-4` |
| Sidebar width | `w-[360px]` |

---

## Surface Hierarchy

1. **Page background** — stone-950, ambient radial gradients
2. **Primary surfaces** — glass effect with backdrop-blur, border-white/8
3. **Card surfaces** — stone-900, border-white/10, hover:border-primary/50
4. **Elevated surfaces** — stone-800, stronger borders
5. **Active/selected** — primary/10 tint, primary/50 border
6. **Hero surfaces** — radial gradient overlays on dark base

---

## Component Constraints

### Cards
- `rounded-2xl` minimum (larger for hero cards: `rounded-[2rem]`)
- `border border-white/10`
- Hover: `hover:-translate-y-1 hover:border-primary/50 hover:shadow-glow`
- No flat cards — always have visible border

### Buttons
- Primary: gradient background (amber to rose)
- Secondary: `border-white/10 bg-black/10`
- Ghost: transparent, text color only
- All buttons: `rounded-xl` minimum
- Disabled: reduced opacity, no glow

### Badges
- `rounded-full` for status badges
- `rounded-lg` for content badges
- Variant-specific colors (success=emerald, warning=amber, error=red)

### Message Bubbles → Speaker Cards
- NOT chat bubbles — use speaker cards with:
  - Agent avatar (colored icon in rounded-xl container)
  - Agent name + subtitle
  - Colored left border OR colored background tint
  - Play button for TTS
  - Expandable citation section

---

## Motion Principles

- **Enter**: fade-up (0.5s ease-out) for new sections
- **Messages**: slide-in-left for agents, slide-in-right for user
- **Hover**: translate-y-1 + border color change + glow
- **Active states**: scale(0.98) on press
- **Voice waves**: 5 bars with staggered animation
- **Loading**: spin animation on loader icons
- **NO** gratuitous motion — motion must clarify state changes

---

## Mobile Rules

- Stack sidebar below main content (no hidden sidebar)
- Hero text scales down from 5xl to 3xl
- Book grid: 1 column on mobile, 2 on tablet
- Discussion: full-width messages, bottom sheet for sidebar tabs
- Conversation sparks: horizontal scroll instead of wrap
- Input area stays fixed at bottom
- Section picker: bottom sheet instead of inline scroll

---

## Responsive Breakpoints

| Name | Width | Layout |
|------|-------|--------|
| Mobile | < 640px | Single column, stacked |
| Tablet | 640-1024px | 2-column grids |
| Desktop | 1024-1280px | Full layout |
| Wide | > 1280px | Max-width container, centered |

---

## Prohibited Patterns

1. Dashboard card mosaics (books are not KPIs)
2. Generic AI chat layout (we have a salon, not a chatbot)
3. Purple gradients by reflex
4. Startup hero cliches ("Powered by AI")
5. Interchangeable chat bubbles with no room identity
6. Neon nightclub cliches in after-dark mode
7. Faux-minimalism that hides the book
8. Dead white space with no information density
9. Flat cards with no interactive feedback
10. Copy that sounds like a to-do app instead of a reading invitation
