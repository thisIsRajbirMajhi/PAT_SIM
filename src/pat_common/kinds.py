"""Pure canonical vocabularies — trajectory / platform type lists + normalizers.

Dependency-free shared core. The simulator keeps using these exact objects
(via thin re-exports in trajectories.py / platform_motion.py), so there is
one source of truth and no drift.
"""

TRAJECTORY_TYPES = (
    "straight", "circular", "figure_eight", "random",
    "spiral", "sinusoidal", "user-defined",
)

_TRAJECTORY_ALIASES = {
    "figure-eight": "figure_eight",
    "figure_8": "figure_eight",
    "figure-8": "figure_eight",
    "figure8": "figure_eight",
    "figure_of_8": "figure_eight",
    "user_defined": "user-defined",
}


def normalize_trajectory_type(raw):
    t = str(raw or "straight").strip().lower().replace(" ", "_")
    return _TRAJECTORY_ALIASES.get(t, t)


PLATFORM_TYPES = ("none", "linear", "circular", "random", "spiral", "figure_of_8")

FIGURE_8_ALIASES = frozenset({
    "figure_of_8", "figure_8", "figure-of-8", "figure-of_8",
    "figure8", "figure-8", "figure_of-8", "eight",
})


def normalize_platform_type(raw):
    t = str(raw or "none").strip().lower().replace(" ", "_")
    if t in FIGURE_8_ALIASES:
        return "figure_of_8"
    return t


__all__ = [
    "TRAJECTORY_TYPES",
    "normalize_trajectory_type",
    "PLATFORM_TYPES",
    "FIGURE_8_ALIASES",
    "normalize_platform_type",
]
