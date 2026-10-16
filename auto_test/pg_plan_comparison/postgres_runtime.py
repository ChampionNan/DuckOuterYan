"""Signal-safe shutdown for the experiment's stopped/reused private PG cluster."""

import signal
import subprocess


def interrupt(signum, _frame):
    raise KeyboardInterrupt('interrupted by signal ' + str(signum))


def stop_private_postgres(pg_bin_dir, pgdata):
    """Finish cleanup even when a second Ctrl+C/SIGTERM arrives during pg_ctl."""
    saved = {sig: signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        subprocess.run([str(pg_bin_dir / 'pg_ctl'), '-D', str(pgdata), '-m', 'fast',
                        '-t', '60', '-w', 'stop'], check=True, timeout=90)
    finally:
        for sig, handler in saved.items():
            signal.signal(sig, handler)
