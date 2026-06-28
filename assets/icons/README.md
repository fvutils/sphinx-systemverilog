# sphinx-systemverilog — brand assets

Icon set for **sphinx-systemverilog**. The mark fuses the three ideas behind the
project: a **document page** (Sphinx docs), **chip pins** (SystemVerilog hardware),
and a **digital waveform** as the page's last line (signals → docs).

## Palette

| Role        | Hex       |
|-------------|-----------|
| Indigo (bg) | `#1E2A4A` → `#0F172A` |
| Cyan        | `#38BDF8` |
| Teal        | `#0EA5A4` / `#2DD4BF` |
| Amber       | `#FBBF24` → `#F59E0B` |
| Paper       | `#F1F5F9` |

## Source (SVG — edit these)

| File | Use |
|------|-----|
| `icon.svg` | **Primary** app icon (chip-page, rounded tile) |
| `icon-flat.svg` | Tile-less, outlined — works on light **and** dark backgrounds |
| `icon-mono.svg` | Single-color, `currentColor` (tintable) — print / UI / stamps |
| `favicon.svg` | **SV monogram** — the small-size / favicon companion mark |
| `logo-horizontal.svg` | Wordmark lockup for **light** backgrounds |
| `logo-horizontal-dark.svg` | Wordmark lockup for **dark** backgrounds |

The five original proposals are kept as `icon-1…5-*.svg` with a `contact-sheet.png`.

## Exports (`png/`)

- App icon: `icon-{48,64,128,180,192,256,512}.png`
- `apple-touch-icon.png` (180×180)
- Favicon (monogram): `favicon-{16,32,48,64}.png`
- `icon-flat-512.png`, `icon-mono-512.png`, `icon-mono-white-512.png` (for dark bg)
- `logo-horizontal.png`, `logo-horizontal-dark.png` (1470×300)

`favicon.ico` — multi-resolution (16/32/48), built from the monogram for crisp
rendering at browser-tab sizes.

## Web usage

```html
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" type="image/svg+xml" href="assets/icons/favicon.svg">
<link rel="apple-touch-icon" href="assets/icons/png/apple-touch-icon.png">
```

## Regenerating exports

Requires `cairosvg` and ImageMagick (`convert`). Re-run the render block in the
project history, or for a single file:

```bash
cairosvg icon.svg -o png/icon-512.png --output-width 512 --output-height 512
```

> Note: use `--output-width/--output-height`, not `-W/-H` (those set the SVG
> container size, not the raster output size).
