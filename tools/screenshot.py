"""Developer helper: save a full screenshot of the main screen.
Usage:  .venv\\Scripts\\python.exe tools\\screenshot.py C:\\path\\to\\shot.png"""
import sys

from PySide6.QtGui import QGuiApplication

app = QGuiApplication(sys.argv[:1])
QGuiApplication.primaryScreen().grabWindow(0).save(sys.argv[1])
