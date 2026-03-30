# Claude Code Opus 4.6 UI Handoff + Google Stitch MCP Roadmap

Last updated: 2026-03-29

Audience:
- Claude Code running Opus 4.6
- A human operator who wants research-first execution
- Future agents inheriting `B:\Projects\Claude\llm-book`

Purpose:
- Step the LLM Book Club UI from "working prototype" to "distinctive product"
- Keep the work code-first, repo-grounded, and incremental
- Use Google Stitch as a design accelerator without letting it become the source of truth

This document is intentionally opinionated. It assumes the current app should feel:
- editorial, intimate, and alive
- more like a live reading salon than a CRUD dashboard
- materially different in standard mode vs after-dark mode
- production-minded enough that design work maps directly to Next.js 15 + Tailwind implementation

## 1. Current Repo Truth

Frontend code that matters most:
- `apps/web/app/page.tsx`
- `apps/web/app/globals.css`
- `apps/web/components/book-shelf.tsx`
- `apps/web/components/session-setup.tsx`
- `apps/web/components/discussion-stage.tsx`
- `apps/web/components/ui/*`

Backend files that shape the UI contract:
- `apps/api/app/routers/sessions.py`
- `apps/api/app/discussion/engine.py`
- `apps/api/app/discussion/agents.py`
- `apps/api/app/discussion/prompts.py`
- `apps/api/app/db/models.py`

Current product facts:
- The app already has multi-agent discussion, citations, SSE streaming, TTS, section-based session setup, and an adult-room path.
- The backend already has an `after_dark_guide` role in flight.
- The frontend was recently improved to better surface session mood and real-time prompts, but the design system is still transitional rather than complete.

Important workspace constraint:
- The worktree is already dirty in backend discussion files. Do not revert or overwrite those changes unless explicitly asked.

## 2. Non-Negotiable Product Direction

The UI should optimize for four emotional outcomes:

1. Anticipation
- The first screen should make opening a book feel like entering an event.

2. Attention
- The discussion UI should make it easier to notice patterns, tensions, citations, and the next good question.

3. Continuity
- Sessions should feel like rooms you return to, not disposable chats.

4. Distinction
- After-dark mode should feel intentionally different from standard mode without becoming tacky, detached, or mechanically sexual.

## 3. What Claude Code Opus 4.6 Should Optimize For

Claude Code should behave as a research-first implementation agent, not a vague design consultant.

Priority order:
1. Preserve backend contracts.
2. Raise the quality of the reading experience.
3. Use Stitch to widen ideation and speed up layout exploration.
4. Port only the strongest Stitch outputs into repo-native React/Tailwind code.
5. Verify each step with targeted checks.

Claude should not:
- treat Stitch output as production-ready by default
- replace grounded discussion UI with generic AI SaaS tropes
- flatten the adult-room experience into purple gradients and cheap seduction
- redesign away the app's core strengths: citations, slice selection, multi-agent tension, live voice

## 4. UI North Star

### Library

Desired feel:
- private library
- live invitations
- not "upload files"

Must communicate:
- what is ready now
- what is worth returning to
- what is best for audio
- why opening a session is attractive tonight

### Session Setup

Desired feel:
- ritualized staging area
- one part editorial preface, one part control room

Must communicate:
- what this session will feel like
- why this slice is worth opening
- what questions will animate the room
- what cast is entering the conversation

### Discussion Stage

Desired feel:
- salon / studio / reading theater
- layered but calm

Must communicate:
- who is speaking
- what the room is trying to understand
- where the evidence lives
- what the reader can ask next without cognitive friction

### After-Dark Mode

Desired feel:
- adult, elegant, candid, text-bound
- never crude, generic, or visually adolescent

Must communicate:
- this is a distinct mode, not just a palette swap
- the lens is interpretive, not pornographic
- desire is being read through text, gesture, power, glamour, delay, self-presentation, and vulnerability

## 5. Research Summary: Google Stitch

Official Google sources indicate that Stitch now supports:
- natural-language generation of high-fidelity UI
- an AI-native infinite canvas
- a project-wide design agent
- agent manager / multi-direction exploration
- interactive prototypes
- voice-based iteration
- `DESIGN.md` for portable design rules
- MCP server + SDK workflows
- exports to downstream developer tools

What matters for this repo:
- Stitch is useful for ideation, screen families, flow concepts, and design-system extraction.
- Stitch should not replace implementation discipline in `apps/web`.
- The highest-value use is not "generate a landing page once"; it is repeated design exploration guided by our actual file structure, modes, and constraints.

Critical distinction:
- Google officially confirms Stitch has an MCP server and SDK, but I did not find an official Google step-by-step Claude Code installation guide for Stitch itself.
- The concrete install flow below uses official Anthropic MCP guidance for Claude Code plus a community-maintained Stitch MCP server that is widely surfaced in MCP directories/GitHub.
- Treat the Stitch package and Google Cloud enablement commands as community-sourced and therefore drift-prone until Google publishes a canonical package/doc path.

Inference:
- The safest operational stance is to use Stitch as a bounded, review-heavy design generation tool, not an always-on autonomous server with broad write authority.

## 6. Research Summary: Claude Code MCP

Anthropic's official Claude Code MCP docs matter here because they define:
- `claude mcp add` for local stdio servers
- `.mcp.json` for project-shared server config
- `claude mcp list`, `claude mcp get`, `claude mcp remove`
- `--scope project` for check-in-able server config
- environment variable expansion in `.mcp.json`
- Windows-specific guidance: local `npx` MCP servers need `cmd /c`

That last point is important for this Windows repo.

## 7. Research Summary: Firebase / Google MCP Config Patterns

Google's Firebase Studio MCP docs are useful as a secondary source for:
- compatible server shapes: stdio, SSE, Streamable HTTP
- passing env vars through config
- config file patterns for agentic environments
- a strong warning that MCP servers can run code and modify the app

That warning applies directly here.

## 8. Recommended Stitch MCP Setup For This Repo

### 8.1 Safety Model

Use Stitch in one of two modes:

1. Exploration mode
- Generate layout directions, variants, and screen ideas.
- Export screenshots/code/assets.
- Port the good parts manually into React/Tailwind.

2. Design-system mode
- Extract design context from the best current screen.
- Generate new screens that inherit its design DNA.
- Maintain consistency across library, setup, and discussion surfaces.

Do not let Stitch:
- directly rewrite large swaths of the codebase
- dictate copy without review
- introduce visual patterns that fight the product's grounded-discussion mechanics

### 8.2 Preconditions

Install/verify:
- Node.js + npm
- Google Cloud SDK (`gcloud`)
- Claude Code

Community Stitch MCP setup currently suggests:

```powershell
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud auth application-default set-quota-project YOUR_PROJECT_ID
gcloud beta services mcp enable stitch.googleapis.com
gcloud auth application-default login
```

This enablement flow is community README-sourced. Verify it against the current repo/docs before depending on it in automation.

### 8.3 Claude Code Project-Scoped Setup

Preferred setup for this repo:

```powershell
claude mcp add stitch --scope project --env GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID -- cmd /c npx -y stitch-mcp
```

Why this form:
- `--scope project` creates a shared `.mcp.json` at repo root
- `cmd /c` is required on native Windows for local `npx` MCP servers per Anthropic docs
- `GOOGLE_CLOUD_PROJECT` keeps config portable

### 8.4 Example `.mcp.json`

If adding by file instead of CLI, use:

```json
{
  "mcpServers": {
    "stitch": {
      "command": "cmd",
      "args": ["/c", "npx", "-y", "stitch-mcp"],
      "env": {
        "GOOGLE_CLOUD_PROJECT": "${GOOGLE_CLOUD_PROJECT}"
      }
    }
  }
}
```

Do not hardcode secrets in `.mcp.json`.

### 8.5 Verification

After setup:

```powershell
claude mcp list
claude mcp get stitch
```

Inside Claude Code:
- use `/mcp` if authentication or approval is required
- confirm the Stitch tools are visible before asking for UI generation work

## 9. Known Community Stitch MCP Tool Surface

Community documentation currently lists these Stitch tools:
- `create_project`
- `list_projects`
- `get_project`
- `list_screens`
- `get_screen`
- `fetch_screen_code`
- `fetch_screen_image`
- `extract_design_context`
- `generate_screen_from_text`

Highest-value tools for this repo:

1. `extract_design_context`
- Use it on the best existing screen to preserve style continuity.

2. `generate_screen_from_text`
- Use it to create variants for library, setup, and discussion screens.

3. `fetch_screen_code`
- Useful for structure ideas, not direct copy-paste into production.

4. `fetch_screen_image`
- Useful for visual review and critique loops.

## 10. Recommended Stitch Workflow For LLM Book Club

### Phase A: Freeze the product intent before generating anything

Before any Stitch call, Claude should write:
- one-sentence visual thesis
- one-sentence product thesis
- one-sentence behavior thesis

For this repo:
- Visual thesis: editorial reading salon with cinematic warmth, live voices, and disciplined restraint.
- Product thesis: every screen should make the user want to open a slice and stay in the conversation.
- Behavior thesis: the UI should reduce friction between curiosity, evidence, and the next question.

### Phase B: Write the repo's design rules into `DESIGN.md`

Create a new file such as:
- `design/llm-book-club.DESIGN.md`

It should capture:
- typography direction
- color logic
- density rules
- component constraints
- adult-room distinctions
- responsive behavior
- prohibited patterns

Suggested contents:
- no dashboard card mosaics
- no generic AI-chat layout
- citations must remain easy to inspect
- discussion stage must preserve strong speaker identity
- adult room uses warmer, lower-light, more intimate composition without becoming explicit visual kitsch
- primary CTA copy must sound like opening a room, not starting a workflow

This file then becomes reusable input for Stitch and for direct coding.

### Phase C: Generate screen families, not one-offs

Ask Stitch for screen sets, not isolated pages:

1. Library family
- desktop landing
- mobile landing
- "continue reading" emphasis variant
- "audio-first tonight" emphasis variant

2. Session setup family
- standard mode
- first-time friendly mode
- after-dark mode

3. Discussion family
- desktop split view
- focus mode
- mobile stacked view
- citation-inspector state
- voice-active state

### Phase D: Use extract-then-generate loops

The best Stitch loop for this repo is:

1. Build one strong screen in Stitch.
2. Extract design context from it.
3. Generate adjacent screens using that extracted context.

This is the fastest route to consistency without hardcoding a full design system up front.

### Phase E: Port only the strongest pieces

Porting rules:
- never port raw Stitch output wholesale
- lift composition, hierarchy, spacing, and interaction ideas
- rewrite implementation in repo-native React + Tailwind
- preserve our real data shape and component contracts

## 11. Code-Focused UI Roadmap

### Sprint 0: Design system baseline

Target files:
- `apps/web/app/globals.css`
- `apps/web/components/ui/*`
- `design/llm-book-club.DESIGN.md`

Tasks:
- define typography scale and spacing system
- formalize role color tokens
- formalize surface hierarchy tokens
- define after-dark visual delta as tokens, not ad hoc classes

Acceptance:
- a new contributor can tell what the visual system is without reading every component

### Sprint 1: Library as invitation

Target files:
- `apps/web/app/page.tsx`
- `apps/web/components/book-shelf.tsx`

Tasks:
- make first viewport poster-like and unmistakable
- improve "continue reading" and "good for audio" treatment
- add stronger shelf storytelling blocks
- create a mobile-first version that still feels premium

Stitch deliverables:
- 3 library hero variants
- 2 mobile library variants
- 1 quiet editorial variant
- 1 more theatrical variant

Acceptance:
- first screen explains product value before the user scrolls
- no generic SaaS-card-first composition remains

### Sprint 2: Session setup as ritual

Target files:
- `apps/web/components/session-setup.tsx`

Tasks:
- deepen the "why this room will work" section
- make slice selection feel like choosing a performance setlist
- surface cast previews more clearly
- make standard and after-dark setup visually distinct while sharing the same structural logic

Stitch deliverables:
- 2 setup desktop variants
- 2 setup mobile variants
- 2 after-dark variants

Acceptance:
- the setup screen makes the user want to press start
- users can tell what kind of session they are building in under 5 seconds

### Sprint 3: Discussion stage as live salon

Target files:
- `apps/web/components/discussion-stage.tsx`

Tasks:
- redesign overall composition around room pulse, live voices, evidence, and reading pane
- create a clearer citation-inspector state
- improve speaking/voice-active choreography
- add mobile conversation ergonomics
- visually differentiate after-dark guide without making the screen noisy

Stitch deliverables:
- 3 discussion variants
- 1 citation-focus state
- 1 audio-active state
- 1 mobile portrait flow

Acceptance:
- speaker changes are immediately legible
- evidence inspection is faster than in the current build
- mobile does not feel like a degraded desktop transplant

### Sprint 4: Prototypes + transitions

Target files:
- `apps/web/app/page.tsx`
- `apps/web/components/session-setup.tsx`
- `apps/web/components/discussion-stage.tsx`

Tasks:
- turn Stitch-generated flow ideas into real navigation/motion specs
- implement a few meaningful transitions
- remove ornamental motion

Acceptance:
- motion clarifies state changes
- no section relies on motion to make sense

## 12. Exact Code Strategy For Porting Stitch Work

### 12.1 Do not generate JSX directly first

First ask Stitch for:
- screen image
- structural code
- design context

Then have Claude translate that into:
- React component shape
- Tailwind classes
- existing UI primitives when useful

### 12.2 Preserve repo-native boundaries

Use this split:

- Layout shell and page composition:
  - `page.tsx`
  - `book-shelf.tsx`
  - `session-setup.tsx`
  - `discussion-stage.tsx`

- Reusable primitives:
  - `apps/web/components/ui/*`

- Global design rules:
  - `globals.css`
  - `DESIGN.md`

Do not:
- let generated styles sprawl inline across all screens
- create one-off utility classes with no token logic
- fork the UI for after-dark mode into separate components unless structurally necessary

### 12.3 Preserve backend truth

Never redesign away:
- session modes
- citation display
- section selection
- experience mode toggle
- role-based message rendering
- voice/TTS affordances

The frontend is a projection layer over real backend state.

## 13. Recommended Claude Prompt Pack For Stitch-Driven Work

### Prompt 1: Establish the visual system

Use when creating `DESIGN.md`:

```text
You are designing the visual system for an AI-native reading salon application.

Product:
- grounded multi-agent book discussion
- citations are core, not decorative
- audio mode matters
- adult mode exists and must feel elegant, candid, and distinct without becoming tacky

Write an agent-friendly DESIGN.md with:
- typography
- color tokens
- spacing rules
- surface hierarchy
- motion principles
- mobile rules
- explicit anti-patterns

Optimize for Next.js + Tailwind implementation, not abstract branding language.
```

### Prompt 2: Library screen family

```text
Design a desktop and mobile screen family for a product called LLM Book Club.

It should feel like entering a private reading salon, not a file uploader.

The screen must:
- foreground books ready to discuss
- foreground sessions worth continuing
- make local audio pairing feel desirable
- make the user want to open a session tonight

Avoid:
- dashboard-card mosaics
- generic AI chatbot tropes
- startup hero clichés

Return a visually bold but implementable concept.
```

### Prompt 3: Session setup family

```text
Design a session setup surface for a grounded multi-agent reading app.

The user chooses:
- mode
- social tone
- slice of book
- audio/text experience
- optional after-dark lens

The screen should feel like staging a room, not filling out a form.

Standard mode and after-dark mode should share a system but feel emotionally distinct.
```

### Prompt 4: Discussion stage family

```text
Design the main live discussion screen for a reading salon app.

Requirements:
- clear speaker identity
- visible room pulse / current agenda
- prompt chips for the next good question
- citations easy to inspect
- optional reading pane
- optional audio-active state
- mobile variant

Do not make it look like Slack, Discord, or a generic AI chat app.
```

### Prompt 5: Extract then extend

```text
Extract the design context from this screen and generate a new adjacent screen that keeps the same visual DNA.

New target screen:
[describe target]

Preserve:
- typography logic
- spacing rhythm
- surface hierarchy
- interaction tone

Change:
- content structure
- local emphasis
- state-specific interaction
```

## 14. Forward-Looking Feature Ideas Stitch Should Help Explore

These are good Stitch ideation targets because they are layout-heavy and product-defining:

1. Reading streak / ritual surface
- "Continue tonight" instead of generic recents

2. Session memory gallery
- memorable claims, favorite citations, unresolved tensions

3. Citation microscope
- hover/expand state that makes quote provenance feel premium and trustworthy

4. Audio choreography panel
- who speaks next, what mode is active, when the room is in listening state

5. After-dark atmosphere controls
- visual warmth, density, and persona treatment tied to the session lens

6. Mobile-first reader mode
- quick prompt actions, citation reveal, speaker cards, finger-friendly evidence drill-down

## 15. What To Build In Code After Stitch Exploration

Short list of likely high-value code changes after the next design pass:

### A. Introduce explicit theme tokens
- add dedicated CSS custom properties for:
  - editorial surfaces
  - live room emphasis
  - citation quality states
  - after-dark accents

### B. Normalize speaker presentation
- centralize role display names, subtitles, colors, and voice metadata
- keep after-dark persona mapping in one place

### C. Create reusable layout primitives
- `ScreenIntro`
- `EditorialPanel`
- `PromptChipRail`
- `VoiceRoster`
- `CitationCard`
- `ModeBanner`

### D. Split discussion stage into focused subcomponents
- current file is carrying too much
- likely extraction targets:
  - `discussion-header.tsx`
  - `discussion-feed.tsx`
  - `discussion-composer.tsx`
  - `discussion-sidebar.tsx`
  - `voice-roster.tsx`
  - `conversation-sparks.tsx`

### E. Add visual states, not just content changes
- typing / composing
- speaking
- citation selected
- reader pane expanded
- after-dark engaged

## 16. Guardrails For Adult Mode

Keep:
- adult
- elegant
- grounded
- psychologically specific
- text-bound

Avoid:
- fetish shorthand
- graphic explicitness
- parody seductress styling
- neon nightclub cliches
- copy that sounds detached from reading

Visual guidance:
- warmer, lower-light, more intimate surface language
- fewer bright accents
- more shadow depth
- better contrast discipline
- premium editorial cues over fantasy cliches

## 17. Operational Checklist For The Next Claude Run

When a future Claude Code Opus 4.6 session picks this up, do this in order:

1. Read this file and `AGENTS.md`.
2. Inspect current diffs with `git status` and `git diff`.
3. Do not touch unrelated dirty backend files.
4. Create `design/llm-book-club.DESIGN.md`.
5. Set up Stitch MCP in project scope only after confirming the operator wants the third-party server installed.
6. Generate library, setup, and discussion variants in Stitch.
7. Export screen images and design context first.
8. Choose one variant per surface.
9. Port only the chosen direction into React/Tailwind.
10. Run targeted verification after each surface.

## 18. Verification Plan

Minimum:

```powershell
cd apps/web
npx tsc --noEmit
```

If Next type stubs are missing, generate or temporarily provide them before the check.

Then:

```powershell
npm run build
```

If build fails due host-level `spawn EPERM`, record that as environmental and continue with targeted TS validation plus code review.

For behavior:
- verify speaker identity rendering
- verify after-dark role rendering
- verify prompt chips still send the intended message
- verify mobile layout in browser
- verify no console errors during stream and audio mode toggles

## 19. Sources

Official:
- Google Labs homepage for Stitch: https://labs.google/
- Google blog, "Introducing vibe design with Stitch" (Mar 18, 2026): https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/
- Google blog, I/O 2025 "Transform ideas into UI designs with Stitch": https://blog.google/technology/ai/io-2025-tools-to-try-globally/
- Google blog, developer updates mentioning Stitch export to CSS/HTML or Figma: https://blog.google/technology/developers/google-ai-developer-updates-io-2025/
- Anthropic Claude Code MCP docs: https://docs.anthropic.com/en/docs/claude-code/mcp
- Anthropic Claude Code settings docs: https://docs.anthropic.com/en/docs/claude-code/settings
- Firebase Studio MCP server docs: https://firebase.google.com/docs/studio/mcp-servers

Community, use with caution:
- `stitch-mcp` GitHub repo by Aakash Kargathara: https://github.com/kargatharaakash/stitch-mcp
- Mirror/summary of the same setup/tool surface: https://mcpservers.org/servers/kargatharaakash/stitch-mcp

## 20. Final Recommendation

The right move is not "replace the frontend with Stitch output."

The right move is:
- formalize our design rules in `DESIGN.md`
- use Stitch to rapidly generate and critique screen families
- extract design context from the best direction
- port the winning layouts into repo-native components
- keep Claude Code Opus 4.6 responsible for code quality, UI consistency, and verification

That is the fastest path to a UI that feels genuinely forward-looking without sacrificing product integrity.
