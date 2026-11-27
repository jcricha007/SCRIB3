"""Map upright artwork to the operator's physical paper mounting."""
from math import isclose

MOUNTS = {
    'top_left_y': 'Top-left home: +Y right, -X down',
    'bottom_left_x': 'Bottom-left home: +X right, +Y up',
}


def validate_mount(mount):
    if not isinstance(mount, str) or mount not in MOUNTS:
        raise ValueError('Choose a supported paper mounting in Paper guide.')
    return mount


def required_travel(width, height, mount):
    validate_mount(mount)
    return (height, width) if mount == 'top_left_y' else (width, height)


def exceeds_travel(required, limits):
    # Allow for conversion through the ten-digit inch display. G-code checks
    # the actual serialized coordinates against the unrounded controller limits.
    return any(limit is not None and size > limit and not isclose(size, limit, rel_tol=1e-9)
               for size, limit in zip(required, limits))


def machine_point(x, y, paper_height, mount):
    """Artwork has a bottom-left origin, rightward x and upward y, in mm."""
    validate_mount(mount)
    return (y - paper_height, x) if mount == 'top_left_y' else (x, y)


def origin_corner(mount):
    validate_mount(mount)
    return 'top-left' if mount == 'top_left_y' else 'lower-left'
