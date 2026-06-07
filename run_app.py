import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    subprocess.check_call(command, cwd=ROOT)


def main() -> None:
    try:
        import streamlit  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])

    run([sys.executable, "-m", "streamlit", "run", str(ROOT / "app.py")])


if __name__ == "__main__":
    main()
