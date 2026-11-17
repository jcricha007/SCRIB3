"""Local artwork import. Converters run without a shell in a temporary folder."""
from dataclasses import dataclass
import os
from pathlib import Path
from math import isfinite
import re
import shutil
import subprocess
import tempfile
from time import monotonic
from xml.etree import ElementTree

from .drawing import read_svg
from .raster import TraceOptions, check_cancel, load_raster, trace_image
from .vector_io import checked_drawing, read_drawing, read_dxf

IMPORT_FORMATS = [('Supported artwork', '*.svg *.ai *.dwg *.psd *.pdf *.png *.dxf *.json'),
                  ('SVG', '*.svg'), ('Adobe Illustrator', '*.ai'), ('AutoCAD DWG', '*.dwg'),
                  ('Photoshop', '*.psd'), ('PDF', '*.pdf'), ('PNG image', '*.png'),
                  ('DXF', '*.dxf'), ('SCRIB3 drawing JSON', '*.json')]
MAX_IMPORT_BYTES = 64_000_000
CONVERTER_TIMEOUT = 90
TOOL_ENV = {'inkscape': 'SCRIB3_INKSCAPE', 'dwg2dxf': 'SCRIB3_DWG2DXF', 'gs': 'SCRIB3_GHOSTSCRIPT'}


def find_converter(name):
    override = os.environ.get(TOOL_ENV[name])
    if override:
        path = Path(override).expanduser()
        if not path.is_file():
            raise ValueError(f'{TOOL_ENV[name]} does not point to an executable file.')
        return str(path.resolve())
    names = ('gswin64c', 'gswin32c', 'gs') if name == 'gs' else (name,)
    for binary in names:
        if found := shutil.which(binary):
            return found
    candidates = [Path('/opt/homebrew/bin') / name, Path('/usr/local/bin') / name]
    if name == 'inkscape':
        candidates += [Path('/Applications/Inkscape.app/Contents/MacOS/inkscape'),
                       Path.home() / 'Applications/Inkscape.app/Contents/MacOS/inkscape',
                       Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Inkscape/bin/inkscape.exe']
    if name == 'gs':
        candidates += sorted((Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'gs').glob('gs*/bin/gswin64c.exe'), reverse=True)
    return next((str(p) for p in candidates if p.is_file()), None)


def require_converter(name):
    found = find_converter(name)
    if found:
        return found
    guidance = {'inkscape': 'Install Inkscape 1.3 or newer. On Mac: brew install --cask inkscape.',
                'dwg2dxf': 'Install GNU LibreDWG. On Mac: brew install libredwg.',
                'gs': 'Legacy PostScript AI requires Ghostscript. On Mac: brew install ghostscript.'}
    raise ValueError(f'{guidance[name]} Alternatively set {TOOL_ENV[name]} to its executable path.')


def run_converter(arguments, folder, cancel=None):
    check_cancel(cancel)
    log = Path(folder) / 'converter.log'
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    environment = os.environ | {'LC_ALL': 'C', 'LANG': 'C',
                                'INKSCAPE_PROFILE_DIR': str(Path(folder) / 'inkscape-profile')}
    with log.open('wb') as output:
        try:
            process = subprocess.Popen(arguments, cwd=folder, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, shell=False, env=environment, **kwargs)
        except OSError as exc:
            raise ValueError('Cannot start the artwork converter. Check its installation and executable path.') from exc
        deadline = monotonic() + CONVERTER_TIMEOUT
        try:
            while process.poll() is None:
                check_cancel(cancel)
                if monotonic() > deadline:
                    raise ValueError('Artwork conversion timed out. Simplify the file or export SVG/PNG from the source app.')
                if log.stat().st_size > 4_000_000:
                    raise ValueError('Converter produced excessive diagnostic output.')
                try:
                    process.wait(timeout=.1)
                except subprocess.TimeoutExpired:
                    pass
            check_cancel(cancel)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
    if log.stat().st_size > 4_000_000:
        raise ValueError('Converter produced excessive diagnostic output.')
    message = log.read_bytes().decode('utf-8', errors='replace').strip()
    if 'no pages selected' in message.lower():
        raise ValueError('That page is not present in this document. Choose another page number.')
    if process.returncode:
        raise ValueError(f'Artwork conversion failed (exit {process.returncode}). {message[-2000:]}')
    return message[-2000:]


@dataclass(frozen=True)
class ImportOptions:
    method: str = 'Vector paths'
    page: int = 1
    trace: TraceOptions = TraceOptions()

    def __post_init__(self):
        if self.method not in ('Vector paths', 'Trace image'):
            raise ValueError('Choose Vector paths or Trace image.')
        if type(self.page) is not int or not 1 <= self.page <= 10000:
            raise ValueError('Page must be a whole number from 1 to 10,000.')
        if not isinstance(self.trace, TraceOptions):
            raise ValueError('Invalid trace settings.')


@dataclass(frozen=True)
class ImportResult:
    drawing: tuple
    note: str
    image: object = None


def _require_output(path):
    if not path.is_file() or not path.stat().st_size:
        raise ValueError('The converter produced no artwork. Check the page number and file compatibility.')
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise ValueError('Converted artwork exceeds 64 MB. Simplify the source file.')


def read_artwork(path, options=None, cancel=None):
    path = Path(path)
    extension = path.suffix.lower()
    if extension not in {'.svg', '.ai', '.dwg', '.psd', '.pdf', '.png', '.dxf', '.json'}:
        raise ValueError('Choose SVG, AI, DWG, PSD, PDF, PNG, DXF, or drawing JSON.')
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise ValueError('Choose artwork under 64 MB.')
    options = options or ImportOptions(method='Trace image' if extension in ('.png', '.psd') else 'Vector paths')
    check_cancel(cancel)
    if extension in ('.svg', '.dxf', '.json'):
        if options.method != 'Vector paths':
            raise ValueError('Use Vector paths for SVG, DXF and drawing JSON.')
        return ImportResult(read_drawing(path), 'Vector paths preserved; artwork is fitted to paper when applied.')
    if extension in ('.png', '.psd'):
        if options.method != 'Trace image':
            raise ValueError('PNG and PSD are raster artwork. Choose Trace image.')
        drawing, image = trace_image(load_raster(path), options.trace, cancel)
        detail = 'PSD uses its saved merged composite. ' if extension == '.psd' else ''
        return ImportResult(drawing, detail + f'{options.trace.mode} trace at {image.width} x {image.height} pixels. '
                            'Tracing approximates the visible artwork; review small details.', image)
    with tempfile.TemporaryDirectory(prefix='scrib3-import-') as temporary:
        folder = Path(temporary)
        source = folder / ('input' + extension)
        shutil.copyfile(path, source)
        if extension == '.dwg':
            if options.method != 'Vector paths':
                raise ValueError('Use Vector paths for DWG model-space drawings.')
            output = folder / 'converted.dxf'
            run_converter([require_converter('dwg2dxf'), '-o', str(output), str(source)], folder, cancel)
            _require_output(output)
            return ImportResult(read_dxf(output), 'DWG converted through LibreDWG; flat model-space paths only. '
                                'Review the result; paper layouts and unsupported CAD entities are not imported.')
        if extension == '.ai':
            with source.open('rb') as stream:
                header = stream.read(1024)
            pdf = folder / 'input.pdf'
            if b'%PDF-' in header:
                source.rename(pdf)
            elif header.startswith(b'%!PS'):
                run_converter([require_converter('gs'), '-dSAFER', '-dBATCH', '-dNOPAUSE',
                               '-sDEVICE=pdfwrite', f'-sOutputFile={pdf}', str(source)], folder, cancel)
                _require_output(pdf)
            else:
                raise ValueError('Save this AI file with Create PDF Compatible File enabled in Illustrator, '
                                 'or export SVG/PDF. Its private Illustrator data cannot be imported.')
            source = pdf
        inkscape = require_converter('inkscape')
        version = re.search(r'Inkscape (\d+)\.(\d+)', run_converter([inkscape, '--version'], folder, cancel))
        if version is None or tuple(map(int, version.groups())) < (1, 3):
            raise ValueError('PDF/AI import requires Inkscape 1.3 or newer for selected-page conversion. Update Inkscape.')
        # An export argument selects Inkscape's command-line mode. --batch-process
        # can start its GUI event loop on Windows and hang even after export.
        base = [inkscape, str(source), '--pdf-poppler', f'--pages={options.page}']
        converted = folder / 'converted.svg'
        run_converter(base + ['--export-plain-svg', '--export-text-to-path', f'--export-filename={converted}'], folder, cancel)
        _require_output(converted)
        if options.method == 'Vector paths':
            try:
                drawing = checked_drawing(read_svg(converted))
            except ValueError as exc:
                raise ValueError(f'Vector conversion needs flattened artwork: {exc} '
                                 'Choose Trace image for a preview of the rendered page.') from exc
            return ImportResult(drawing, f'Page {options.page}: vector paths preserved. Text becomes glyph outlines, '
                                'not single-stroke lettering. Artwork is fitted to paper when applied.')
        output = folder / 'rendered.png'
        # Bound both raster dimensions, including unusually tall/narrow pages.
        try:
            viewbox = ElementTree.parse(converted).getroot().attrib['viewBox'].replace(',', ' ').split()
            width, height = map(float, viewbox[2:])
            if not all(isfinite(v) and v > 0 for v in (width, height)):
                raise ValueError()
            pixels = int(options.trace.resolution * width / max(width, height))
            if pixels < 1:
                raise ValueError()
        except (KeyError, ValueError, ElementTree.ParseError) as exc:
            raise ValueError('The converted page has invalid or excessively narrow dimensions.') from exc
        run_converter([inkscape, str(converted), '--export-area-page',
                       f'--export-width={pixels}', f'--export-filename={output}'], folder, cancel)
        _require_output(output)
        drawing, image = trace_image(load_raster(output), options.trace, cancel)
        return ImportResult(drawing, f'Page {options.page}: {options.trace.mode.lower()} trace of the rendered page '
                            f'at {image.width} x {image.height} pixels. Review small details.', image)
