import importlib
import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--mdr-backend":
        # A frozen GUI and its headless host share this EXE. Close the optional
        # PyInstaller splash before dispatching so the service never opens a GUI.
        try:
            splash = importlib.import_module("pyi_splash")
            splash.close()
        except Exception:
            pass
        from backend.__main__ import main as backend_main

        raise SystemExit(backend_main(sys.argv[2:]))

    from gui.app import main as gui_main
    gui_main()

if __name__ == "__main__":
    main()
