"""iOS device profiles for the BoboXcode QEMU simulator."""

DEVICE_PROFILES = {
    "iphone15": {
        "name": "iPhone 15", "width": 393, "height": 852,
        "ram_mb": 6144, "cores": 4, "scale": 3.0,
    },
    "iphone15_pro": {
        "name": "iPhone 15 Pro", "width": 393, "height": 852,
        "ram_mb": 8192, "cores": 6, "scale": 3.0,
    },
    "ipad_pro_13": {
        "name": 'iPad Pro 13"', "width": 1032, "height": 1376,
        "ram_mb": 8192, "cores": 8, "scale": 2.0,
    },
    "iphone_se": {
        "name": "iPhone SE (3rd gen)", "width": 375, "height": 667,
        "ram_mb": 4096, "cores": 4, "scale": 2.0,
    },
}


def list_devices():
    """Return [(key, display_name), ...] for the device selector UI."""
    return [(k, v["name"]) for k, v in DEVICE_PROFILES.items()]


def get_profile(key: str) -> dict:
    return DEVICE_PROFILES.get(key, DEVICE_PROFILES["iphone15"])
