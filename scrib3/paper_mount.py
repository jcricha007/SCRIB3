"""Map upright artwork to the operator's physical paper mounting."""

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


def machine_point(x, y, paper_height, mount):
    """Artwork has a bottom-left origin, rightward x and upward y, in mm."""
    validate_mount(mount)
    return (y - paper_height, x) if mount == 'top_left_y' else (x, y)


def origin_corner(mount):
    validate_mount(mount)
    return 'top-left' if mount == 'top_left_y' else 'lower-left'
