---
version: alpha
name: 全民查證公社 — Frame (demo_v0.4.0)
description: >
  Frame-scale design system for the progress-report demo film. The film borrows the product's own
  visual language (code/frontend/src/index.css): white and #F7F7F8 surfaces, one ink (#111111),
  no brand accent colour. Red / yellow / green exist ONLY inside the captured UI, where the product
  itself shows a verdict. Emphasis is made with ink inversion, weight, scale and structure, never hue.
unit: the frame — 1920×1080, 30 fps
principle: every UI pixel is a genuine capture · the film only frames, magnifies and labels it

colors:
  stage: "#F7F7F8"          # frame background behind panels
  paper: "#FFFFFF"          # panels, cards, the hook and end cards
  ink: "#111111"            # text, inverted pills, terminal surface, phone frame
  ink-soft: "#3F3F46"       # secondary text on paper/stage (10.4:1 on white)
  ink-muted: "#5B5B66"      # labels, captions of captions (6.6:1 on white, 6.2:1 on stage)
  line: "#D4D4D8"           # 2px rules and panel borders
  line-soft: "#E4E4E7"      # grid texture, inner dividers
  tint: "#ECECEE"           # neutral highlight behind a marked line (no yellow marker)
  on-ink: "#FFFFFF"         # text on ink
  on-ink-muted: "#A1A1AA"   # secondary text on ink (7.6:1 on #111)
  mask: "#C9C9CF"           # the obscured-URL block (no real URL text sits underneath)

radii:
  panel: "20px"
  card: "16px"
  pill: "999px"
  phone: "46px"

typography:
  cjk-stack: '"Microsoft JhengHei", "Noto Sans TC", sans-serif'   # system CJK stack, owner's choice
  mono-stack: '"JetBrains Mono", "Microsoft JhengHei", monospace'  # bundled mono + CJK fallback
  display:  { px: 104, weight: 700, lineHeight: 1.22, tracking: "0.01em" }   # hook lines, end-card name
  h1:       { px: 68,  weight: 700, lineHeight: 1.2 }
  h2:       { px: 46,  weight: 700, lineHeight: 1.25 }
  body:     { px: 32,  weight: 400, lineHeight: 1.5, color: "ink-soft" }
  body-strong: { px: 32, weight: 700, lineHeight: 1.45 }
  label:    { px: 24,  weight: 700, lineHeight: 1.3 }                        # pills, honesty tags
  mono:     { px: 24,  weight: 400, lineHeight: 1.55 }                       # terminal, JSON, ids
  eyebrow:  { px: 22,  weight: 700, tracking: "0.12em", family: "mono-stack", color: "ink-muted" }
  stat:     { px: 120, weight: 700, lineHeight: 1.0, numeric: "tabular-nums" }
  caption:  { px: 44,  weight: 700, lineHeight: 1.2, color: "on-ink" }

spacing:
  margin-x: "96px"            # action-safe; key content never leaves x 96–1824
  content-top: "76px"         # below the persistent chrome band
  content-bottom: "876px"     # above the caption band
  caption-band: "y 892–972"   # single line, centred, inside title-safe (bottom 972)
  column-gap: "48px"
  footage-panel: "1140×800 at (96,76)"   # desktop captures; right column x 1284–1824

components:
  footage-panel:
    backgroundColor: "{colors.paper}"
    border: "2px solid {colors.line}"
    rounded: "{radii.panel}"
    shadow: "0 24px 60px rgba(17,17,17,0.10)"
    description: "Window onto a 1920×1080 capture. A virtual camera (scale 1.0 wide → 1.425 tight on the 800px content column) moves INSIDE the panel; the panel itself never distorts the UI. No browser chrome, no fake URL bar."
  phone-frame:
    border: "10px solid {colors.ink}"
    rounded: "{radii.phone}"
    description: "Plain rounded frame around the 390×844 capture. No notch, no status bar, no hardware details."
  magnifier:
    backgroundColor: "{colors.paper}"
    border: "2px solid {colors.ink}"
    rounded: "{radii.card}"
    description: "A second view of the SAME footage at ~1.9× so phone-sized text is legible. Always tied to the phone by a hairline connector."
  ink-pill:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    rounded: "{radii.pill}"
    typography: "{typography.label}"
    description: "Honesty tags (模擬模式…, 本機執行畫面, 畫面加速 ×N) and active ladder steps."
  ghost-pill:
    backgroundColor: "{colors.paper}"
    border: "2px solid {colors.line}"
    textColor: "{colors.ink-soft}"
    rounded: "{radii.pill}"
    description: "Inactive ladder steps, secondary tags."
  note-card:
    backgroundColor: "{colors.paper}"
    border: "2px solid {colors.line}"
    rounded: "{radii.card}"
    description: "Right-column explanation cards; one idea each, eyebrow + strong line + optional body."
  terminal:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    rounded: "{radii.panel}"
    typography: "{typography.mono}"
    description: "Re-drawn from the captured stdout (text verbatim). Labelled 終端機實際輸出・畫面重繪. No OS window chrome."
  caption:
    backgroundColor: "rgba(17,17,17,0.94)"
    textColor: "{colors.on-ink}"
    rounded: "18px"
    typography: "{typography.caption}"
    description: "One narration line at a time, bottom centre."
  chrome:
    description: "Persistent top band: brand word-mark left, chapter eyebrow right, 3px ink progress rule along the top edge."
  stage-texture:
    description: "48px hairline grid ({colors.line-soft}) on the stage, fading toward the centre; static structure, ambient motion comes from the progress rule and content."
---

# 全民查證公社 — Frame

## Overview

A plain-spoken product film. The register is a well-made internal demo: calm, exact, slightly
editorial. The product's UI is already black-on-white with colour reserved for verdicts, so the film
does the same — it never competes with a red 「詐騙警告」 by adding colour of its own.

## The Frame

- Stage `#F7F7F8` with a hairline grid; white panels float on it with a 2px border and one soft shadow.
- Left-anchored footage, right-hand explanation column; captions own the bottom band. Nothing is
  centred-and-floating except the hook and the end card, where stillness is the point.
- Two focal points per frame: the capture (what happened) and one note (what it means).

## Composition Rules

- Do: label every capture honestly (本機執行畫面 / 模擬模式… / 畫面加速 ×N / 畫面重繪).
- Do: make small UI legible with the camera or the magnifier, never by redrawing the UI.
- Do: keep numbers exactly as approved; count-ups land on the exact figure.
- Don't: add red, yellow or green outside captured UI. Don't use emoji except inside captured reply text.
- Don't: imitate Threads, a phone OS, a browser or an OS terminal window.
- Don't: show the suspicious URL. The mask block has no URL text underneath it.

## Motion

Medium energy. Entrances 0.35–0.6s with varied eases (power3.out, expo.out, back.out for pills);
camera moves 0.9–1.2s power2.inOut; primary scene transition is a push slide (0.5s power3.inOut),
blur crossfade marks topic changes (into the product, into the numbers, into the close). The last
scene fades out; nothing else animates out before a transition.
