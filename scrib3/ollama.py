from __future__ import annotations

import json
from math import isfinite
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .drawing import Drawing, Stroke

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["strokes"],
    "properties": {
        "strokes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 60,
            "items": {
                "type": "array",
                "minItems": 2,
                "maxItems": 120,
                "items": {
                    "type": "array",
                    "minItems": 2,
                    "maxItems": 2,
                    "items": {"type": "number", "minimum": 0, "maximum": 1000},
                },
            },
        }
    },
}

SYSTEM_PROMPT = (
    "You design drawable pen-plotter line art. Return only a JSON object with a strokes "
    "array. Each stroke is an array of [x,y] points connected by straight lines. "
    "The canvas is 1000 units square, with x right and y down. A new stroke lifts "
    "the pen. Use at most 60 strokes, use 2 to 120 points per stroke, and keep every "
    "coordinate between 0 and 1000. Prefer distinctive silhouettes and sparse interior "
    "details. Close loops by repeating their first point. Do not use fills or prose."
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def parse_drawing(content: str) -> Drawing:
    result = json.loads(content)
    if not isinstance(result, dict) or set(result) != {"strokes"}:
        raise ValueError("Ollama returned an invalid drawing object.")
    raw_strokes = result["strokes"]
    if not isinstance(raw_strokes, list) or not 1 <= len(raw_strokes) <= 60:
        raise ValueError("Ollama returned an invalid number of strokes.")
    drawing: list[Stroke] = []
    for stroke in raw_strokes:
        if not isinstance(stroke, list) or not 2 <= len(stroke) <= 120:
            raise ValueError("Ollama returned a stroke with an invalid length.")
        points: list[tuple[float, float]] = []
        for point in stroke:
            if not isinstance(point, list) or len(point) != 2 or not all(
                type(value) in (int, float) and 0 <= value <= 1000 and isfinite(value)
                for value in point
            ):
                raise ValueError("Ollama returned a point outside the drawing area.")
            xy = (float(point[0]), float(point[1]))
            if not points or xy != points[-1]:
                points.append(xy)
        if len(points) > 1:
            drawing.append(tuple(points))
    if not drawing:
        raise ValueError("Ollama returned no drawable strokes. Try a simpler prompt.")
    return tuple(drawing)


def generate_drawing(model: str, prompt: str) -> Drawing:
    model, prompt = model.strip(), prompt.strip()
    if not model or not prompt:
        raise ValueError("Enter an installed Ollama model name and a drawing prompt.")
    if "cloud" in model.lower():
        raise ValueError("Choose a locally installed model tag.")
    if len(prompt) > 12_000:
        raise ValueError("Use a drawing prompt of 12,000 characters or fewer.")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0.2, "num_predict": 8192},
    }
    request = Request(
        "http://127.0.0.1:11434/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=180) as response:
            raw = response.read(1_000_001)
    except HTTPError as exc:
        raise ValueError(f"Ollama returned HTTP {exc.code}. Check the installed model tag.") from exc
    except (URLError, TimeoutError) as exc:
        raise ValueError(f"Ollama is unreachable or timed out. Check that it is running. {exc}") from exc
    if len(raw) > 1_000_000:
        raise ValueError("Ollama returned an oversized drawing.")
    response = json.loads(raw)
    try:
        content = response["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Ollama did not return drawing content.") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Ollama returned an empty drawing. Try a simpler prompt.")
    return parse_drawing(content)
