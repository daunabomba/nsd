import subprocess
import os
import multiprocessing
import shutil
from pathlib import Path
from mods import colors
from mods.build import get_build_env, SubprocessRunner


# Module-level runner, initialized when needed
_runner = None

def _get_runner(trace_file=None):
    """Get or create the subprocess runner."""
    global _runner
    if _runner is None:
        _runner = SubprocessRunner(trace_file)
    return _runner

def set_trace_file(trace_file):
    """Set the trace file for subprocess logging."""
    global _runner
    _runner = SubprocessRunner(trace_file)

def target_configure(staging_dir: Path, target_dir: Path, arch="x32"):
    colors.info(f"NSD: target_configure ({arch})")
    repo_root = Path(__file__).parent
    
    # Initialize submodules if necessary (simdzone is required)
    if not (repo_root / "simdzone" / "include" / "zone.h").exists():
        colors.info("NSD: initializing submodules...")
        _get_runner().run(["git", "submodule", "update", "--init", "--recursive"], cwd=repo_root, check=True)

    # Generate configure script if it doesn't exist
    if not (repo_root / "configure").exists():
        colors.info("NSD: running autoreconf...")
        _get_runner().run(["autoreconf", "-fi"], cwd=repo_root, env=get_build_env(), check=True)

    std_flags = os.environ.get("CFLAGS", "")
    static_flags = os.environ.get("CFLAGS_STATIC", std_flags)
    
    # We need to point to OpenSSL in staging
    ssl_path = staging_dir / "usr"
    
    host_triple = {
        "x32": "x86_64-linux-muslx32",
        "x86_64": "x86_64-linux-musl",
        "aarch64": "aarch64-linux-musl",
        "riscv64": "riscv64-linux-musl",
    }.get(arch, "x86_64-linux-musl")

    cmd = [
        "./configure",
        f"--host={host_triple}",
        "--prefix=/usr",
        "--sbindir=/usr/bin",
        f"--with-ssl={ssl_path}",
        "--with-libevent=no",
        "--disable-dnstap",
        "--disable-flto",
        f"CC=clang {std_flags}",
        f"LDFLAGS={static_flags}",
    ]
    
    _get_runner().run(cmd, cwd=repo_root, env=get_build_env(), check=True)

def target_build(staging_dir: Path, target_dir: Path, arch="x32"):
    colors.info(f"NSD: target_build")
    repo_root = Path(__file__).parent
    make_jobs = multiprocessing.cpu_count()
    _get_runner().run(["make", f"-j{make_jobs}"], cwd=repo_root, env=get_build_env(), check=True)

def target_install(staging_dir: Path, target_dir: Path, arch="x32"):
    colors.info(f"NSD: target_install")
    repo_root = Path(__file__).parent
    
    # Install to staging
    colors.info(f"NSD: installing to staging {staging_dir}")
    _get_runner().run(["make", f"DESTDIR={staging_dir}", "install"], cwd=repo_root, env=get_build_env(), check=True)
    
    # Install to target
    colors.info(f"NSD: installing to target {target_dir}")
    _get_runner().run(["make", f"DESTDIR={target_dir}", "install"], cwd=repo_root, env=get_build_env(), check=True)
    
    # Prune target image
    colors.info(f"NSD: pruning development files and documentation from target...")
    shutil.rmtree(target_dir / "usr" / "include", ignore_errors=True)
    shutil.rmtree(target_dir / "usr" / "share" / "man", ignore_errors=True)
    # Remove static libs if any
    for lib in (target_dir / "usr" / "lib").glob("*.a"):
        lib.unlink()
