# Apptainer bind helper
def _apptainer_binds(paths: list) -> str:
    """
    Apptainer generally needs the path to be expliciting stated if they are not part of the
    build image. In most cases we need to bind the path when we run each tool.
    For each path we bind its top-level mount point so the same string works
    on LUNARC (/lunarc/nobackup/...) and on cloud (s3-fuse mounts, /data, etc.)
    The actual paths are passed directly no hardcoding of /lunarc anywhere.

    Example:
        _apptainer_binds(["/path/to/project", "/path/to/results"])
        -> "--bind /path/to/project:/path/to/project
            --bind /path/to/results:/path/to/results"
    """
    seen = set()
    flags = []
    for p in paths:
        # Use the path itself (file or directory), it will accept both
        mount = str(Path(p).resolve())
        if mount not in seen:
            seen.add(mount)
            flags.append(f"--bind {mount}:{mount}")
    return " ".join(flags)
