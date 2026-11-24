"""PyInstaller entry script for VoxDock.exe."""
import multiprocessing

from app.launcher import run

if __name__ == "__main__":
    multiprocessing.freeze_support()
    run()
