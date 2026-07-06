"""Test helpers for compiling and running generated C with gcc.

`find_gcc` looks for gcc on PATH first (the normal case for a grader or a fresh
terminal), then honors an optional AUJAVA_GCC override, then falls back to
scanning a WinLibs winget install on Windows. Tests that need gcc skip
themselves gracefully if none is found.
"""

import glob
import os
import shutil
import subprocess
import tempfile


def find_gcc():
    gcc = shutil.which("gcc")
    if gcc:
        return gcc
    override = os.environ.get("AUJAVA_GCC")
    if override and os.path.exists(override):
        return override
    pattern = os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\*WinLibs*\mingw64\bin\gcc.exe"
    )
    matches = glob.glob(pattern)
    if matches:
        return matches[0]
    return None


def compile_and_run(c_source, timeout=20):
    """Compile C source with gcc and run it; return the program's stdout.

    Raises RuntimeError (with the compiler output and offending source) if gcc
    fails to compile the generated code.
    """
    gcc = find_gcc()
    if gcc is None:
        raise RuntimeError("gcc not found")

    workdir = tempfile.mkdtemp(prefix="aujava_")
    c_path = os.path.join(workdir, "out.c")
    exe_path = os.path.join(workdir, "out.exe")
    with open(c_path, "w", encoding="utf-8") as f:
        f.write(c_source)

    compiled = subprocess.run(
        [gcc, c_path, "-o", exe_path],
        capture_output=True, text=True, timeout=timeout,
    )
    if compiled.returncode != 0:
        raise RuntimeError(
            "gcc failed to compile generated C:\n"
            + compiled.stderr
            + "\n--- generated C ---\n"
            + c_source
        )

    run = subprocess.run([exe_path], capture_output=True, text=True, timeout=timeout)
    return run.stdout
