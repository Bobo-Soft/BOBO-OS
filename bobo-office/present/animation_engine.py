"""
BoboPresent animation engine.
Registry of element animations and slide transitions with parameters. Produces
serializable animation specs used by the editor preview and the video exporter
(which maps them to ffmpeg fade/zoom filters).
"""

ELEMENT_ANIMATIONS = {
    "appear":      {"duration": 0.3, "ffmpeg": "fade=t=in"},
    "disappear":   {"duration": 0.3, "ffmpeg": "fade=t=out"},
    "typewriter":  {"duration": 1.2, "ffmpeg": None},
    "bounce":      {"duration": 0.6, "ffmpeg": None},
    "pulse":       {"duration": 0.5, "ffmpeg": None},
    "slide_in":    {"duration": 0.4, "ffmpeg": None},
    "zoom_in":     {"duration": 0.4, "ffmpeg": "zoompan"},
    "fade_in":     {"duration": 0.4, "ffmpeg": "fade=t=in"},
}

SLIDE_TRANSITIONS = {
    "none": "", "fade": "fade", "slide": "slideleft", "slideright": "slideright",
    "zoom": "zoomin", "flip": "hlwind", "cube": "cube", "wipe": "wipeleft",
    "dissolve": "dissolve", "circleopen": "circleopen", "radial": "radial",
    "pixelize": "pixelize", "smoothleft": "smoothleft", "smoothright": "smoothright",
    "wipeup": "wipeup", "wipedown": "wipedown", "slideup": "slideup",
    "slidedown": "slidedown", "fadeblack": "fadeblack", "fadewhite": "fadewhite",
    "distance": "distance", "squeezev": "squeezev", "squeezeh": "squeezeh",
    "hblur": "hblur", "diagtl": "diagtl", "diagtr": "diagtr", "diagbl": "diagbl",
    "diagbr": "diagbr", "hlslice": "hlslice", "vuslice": "vuslice", "coverleft": "coverleft",
}


def list_element_animations():
    return list(ELEMENT_ANIMATIONS.keys())


def list_transitions():
    return list(SLIDE_TRANSITIONS.keys())


def xfade_name(transition: str) -> str:
    """Map a friendly transition to an ffmpeg xfade filter name (default fade)."""
    return SLIDE_TRANSITIONS.get(transition, "fade") or "fade"


def spec_for(element_anim: str) -> dict:
    return ELEMENT_ANIMATIONS.get(element_anim, ELEMENT_ANIMATIONS["appear"])
