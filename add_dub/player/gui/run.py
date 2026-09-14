import sys
from PySide6.QtWidgets import QApplication, QMessageBox
from add_dub.player.config.defaults import APP_NAME
from .window import Window


def main(args):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    try:
        window = Window()
    except (OSError, RuntimeError) as exc:
        QMessageBox.critical(None, APP_NAME, str(exc))
        return 1
    window.show()
    if args.input:
        window.open_video(args.input[0])
    return app.exec()
