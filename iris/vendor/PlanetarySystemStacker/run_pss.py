"""Start the upstream PSS console workflow without importing its GUI entry point."""
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent
if (current_dir / 'planetary_system_stacker').exists():
    vendor = current_dir / 'planetary_system_stacker'
elif (current_dir / 'vendor' / 'PlanetarySystemStacker' / 'planetary_system_stacker').exists():
    vendor = current_dir / 'vendor' / 'PlanetarySystemStacker' / 'planetary_system_stacker'
else:
    vendor = current_dir
sys.path.insert(0, str(vendor))

from PyQt5 import QtCore
from pss_console import PssConsole


class Console(PssConsole):
    failed = False

    def report_error(self, message):
        self.failed = True
        super().report_error(message)

    def next_job_after_error(self, message):
        self.failed = True
        super().next_job_after_error(message)

    def stop_execution(self):
        self.thread.quit()
        self.thread.wait()
        QtCore.QCoreApplication.instance().exit(1 if self.failed else 0)


if __name__ == '__main__':
    app = QtCore.QCoreApplication(sys.argv)
    # Keep the controller alive until all queued workflow signals are handled.
    console = Console()
    sys.exit(app.exec_())
