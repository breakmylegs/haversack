"""Install Keepsake on this PC from the unzipped package (ADR-0038, P5).

Double-click this file, or run ``python install.pyw`` in this folder. It copies
Keepsake into your user's own program folder, sets it to start when you sign
in, and opens it. Nothing needs administrator rights. ``python install.pyw
--uninstall`` removes the program and the start-up entry, never your settings
or saves.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "py_modules"))

from keepsake import pcinstall  # noqa: E402

if __name__ == "__main__":
    sys.exit(pcinstall.main(HERE, sys.argv[1:]))
