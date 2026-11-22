# Import artwork

Choose **Import drawing**. SVG, DXF and drawing JSON use the existing vector
workflow. AI, DWG, PSD, PDF and raster images open a conversion preview. Conversion runs
locally in a worker so the desktop stays responsive. The workspace changes only
after **Use drawing**; **Undo design** restores the previous source. Closing or
cancelling the dialog discards its result. Changing tracing settings or changing
the workspace drawing requires a new preview before applying.

All imported artwork is fitted to the selected paper and margin. This is not a
1:1 CAD-scale import. The regular quality cleanup, reviewed G-code generation,
dry-run and machine checks still apply. Importing never sends motion commands.

| Input | Route into SCRIB3 | Supported content and limits |
| --- | --- | --- |
| SVG | svgelements | Existing vector paths/shapes/transforms. Live text, raster images, clipping, masks and filters require conversion first. |
| AI | Inkscape; Ghostscript for legacy PostScript | PDF-compatible Illustrator files and legacy PostScript AI. Private Illustrator-only data must be saved with **Create PDF Compatible File**, or exported as SVG/PDF. |
| DWG | GNU LibreDWG `dwg2dxf`, then ezdxf | Flat model-space paths supported by the DXF reader. Layouts, 3D objects, dimensions, hatches, live text, unresolved references and unsupported entities require flattening/exploding in CAD first. DWG version/entity support depends on LibreDWG. |
| PSD | Pillow saved merged image, then tracing | Supported 8-bit RGB/gray/CMYK PSD composites. Enable **Maximize Compatibility** when saving in Photoshop. Layers, editable text and Photoshop effects are represented by the saved composite; they are not imported as editable objects. Unsupported PSD modes should be exported as PNG. |
| PDF | Inkscape Poppler import | Select one page. Vector mode preserves path geometry; text becomes glyph outlines. Use **Trace image** for scanned documents, embedded images or clipped/masked artwork that the vector reader rejects. |
| PNG | Pillow, then tracing | Grayscale/RGB/RGBA images; transparency is composited against the selected light/dark background. |
| JPEG/JPG, BMP | Pillow, then tracing | Direct local decoding. JPEG EXIF orientation is honored. |
| WebP, TIFF/TIF | Pillow, then tracing | Static WebP and single-page TIFF only; export an individual frame/page as PNG when needed. |
| DXF / JSON | Existing readers | See [vector formats](vector-formats.md). |

Vector mode plots outlines, not colors, filled shading or line-weight changes.
Raster extensions must match the actual file contents. Raster tracing approximates the visible image; it cannot recover exact curves
or details absent from the source. Large solid areas are especially different
between the two trace modes. Compare the source image and pen paths before
applying. Multi-pen/color separation is not part of this import pass.

## Trace controls

- **Centerline** reduces dark strokes to a skeleton and follows its branches and
  cycles. This is the default for line drawings and avoids automatically drawing
  both edges of a thick raster line. Isolated pixels become short pen marks.
- **Outline** follows boundaries, including holes, and is useful for silhouettes.
  It deliberately traces both sides of a thick line.
- **Threshold** controls which pixels become ink (1–254; default 128).
- **Light ink on dark background** inverts tracing. Transparent pixels use a dark
  background in this mode, allowing light artwork on transparency.
- **Resolution** limits the longest image dimension (128–2048 px; default 1024).
  Downsampling can remove fine detail or close tiny gaps; increase resolution
  when needed and compare the preview.
- **Remove specks** removes connected ink components at or below that pixel area.
  Default 0 preserves them. This can remove deliberate dots, so use it selectively.

Traced polylines are simplified at 0.35 image pixels before the workspace's
millimeter quality tolerance. Both approximations are separate from machine
accuracy. Raster limits are 25 million source pixels, 200,000 skeleton pixels,
2,000 output strokes and 100,000 output points. Complex traces fail explicitly;
reduce resolution or remove noise to retry. Source files are limited to 64 MB;
the existing SVG/DXF/JSON reader limits also apply to converted vectors.

## Install converters

Install the updated `requirements.txt`; the Mac launcher does this on every run.
Pillow and scikit-image are included. Native converters are detected on PATH,
in the standard Inkscape application folders, and in Homebrew's usual locations.

On a Mac with Homebrew:

```bash
brew install --cask inkscape
brew install libredwg ghostscript
```

Use Inkscape 1.3 or newer. On Ubuntu, older distribution packages may need
the [official stable PPA](https://wiki.inkscape.org/wiki/Installing_Inkscape).
On Windows, install
[Inkscape](https://inkscape.org/release/) and download the Windows build of
[GNU LibreDWG](https://github.com/LibreDWG/libredwg/releases). For legacy
PostScript AI, install [Ghostscript](https://ghostscript.com/releases/gsdnld.html).
If a tool is in a custom location, set its environment variable to the actual
executable path before starting SCRIB3:

| Variable | Executable |
| --- | --- |
| `SCRIB3_INKSCAPE` | `inkscape` / `inkscape.exe` |
| `SCRIB3_DWG2DXF` | `dwg2dxf` / `dwg2dxf.exe` |
| `SCRIB3_GHOSTSCRIPT` | `gs` / `gswin64c.exe` |

Converters run as separate processes, with argument lists (no shell), temporary
input/output copies, cancellation and a 90-second limit per conversion stage.
Direct raster formats use the existing Pillow decoder, not a subprocess. Original files are not overwritten. Missing tools and failed conversions produce
an explanation in the preview dialog. No file is uploaded to a conversion service.
LibreDWG can emit null DXF identifiers and repeat identifiers on block-end markers.
SCRIB3 regenerates those identifiers above all existing IDs on the temporary copy
and removes extra unmatched block-end markers. The preview reports these repairs;
coordinates, layers and block definitions are retained. Duplicate IDs on drawing
entities, orphaned block geometry, other invalid geometry and unsupported content
still fail explicitly.

Export continues to produce SVG, DXF, drawing JSON or reviewed G-code. SCRIB3
does not write native AI, DWG or layered PSD documents in this release.

## Research behind this pass

[Drawscape's SVG optimizer](https://drawscape.io/resources/optimize) exposes
vpype merging, simplification, sorting and loop-entry concepts. Its
[single-stroke font tool](https://drawscape.io/resources/single-stroke-fonts)
and customizable blueprint layout suggest useful future lettering/layout work.
The [Drawscape toolkit](https://github.com/drawscape-labs/toolkit) is aimed at
publishing artwork to its API and uses Inkscape group labels for pen assignments.
SCRIB3 uses these as workflow references; no Drawscape artwork or publishing API
is incorporated.

The [pen-plotter topic](https://github.com/topics/pen-plotter) and
[awesome-plotters](https://github.com/beardicus/awesome-plotters) led to these
additional candidates:

| Resource | Decision |
| --- | --- |
| [Inkscape](https://wiki.inkscape.org/wiki/Using_the_Command_Line) | Integrated as the PDF/AI conversion process. Native command-line tests determine supported flags and page-error behavior. |
| [Pillow](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html) | Integrated for raster decoding (including saved PSD composites), alpha handling and downsampling. |
| [scikit-image](https://scikit-image.org/docs/stable/api/skimage.morphology.html#skimage.morphology.skeletonize) | Integrated for skeletonization, contours and polyline simplification. |
| [LibreDWG](https://www.gnu.org/software/libredwg/) | Integrated as an optional external DWG-to-DXF converter. |
| [AutoTrace](https://github.com/autotrace/autotrace) | Reviewed its centerline/outline and despeckle workflow. The initial built-in tracer uses scikit-image, avoiding another native install for PNG/PSD. |
| [linedraw](https://github.com/LingDong-/linedraw) | Reviewed for future sketch/hatch rendering. Stylization is not applied to engineering line art by default. |
| [GRBL-Plotter](https://github.com/svenhb/GRBL-Plotter) | Reviewed image import, Hershey text, layer grouping and preview workflows. SCRIB3 keeps its Mac-compatible desktop and existing GRBL runner. |

