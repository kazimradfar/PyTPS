# Third-party software

PyTPS itself is released under the MIT licence (`LICENSE`). The Windows program (setup and portable zip) also
contains Python and the packages below, each under its own licence. Their copyright stays with their authors.

| Component | Licence | Source |
|---|---|---|
| Python | Python Software Foundation License | https://www.python.org |
| PySide6 / Qt for Python, Qt 6 libraries | GNU LGPL v3 | https://code.qt.io, https://www.qt.io/download-open-source |
| NumPy | BSD 3-Clause | https://numpy.org |
| SciPy | BSD 3-Clause | https://scipy.org |
| scikit-image | BSD 3-Clause | https://scikit-image.org |
| pydicom | MIT | https://pydicom.github.io |
| PyInstaller bootloader | GPL v2 with the PyInstaller bootloader exception | https://pyinstaller.org |
| Inno Setup (creates the setup program) | Inno Setup licence | https://jrsoftware.org/isinfo.php |

Dependencies of these packages that are bundled with them keep their own licences as well.

## Qt / PySide6 (LGPL v3)

PyTPS uses Qt through PySide6 without modifying it. In the Windows program the Qt and PySide6 libraries are
separate files (DLLs) in the program folder, so they can be replaced by another compatible version. The
source code of Qt and PySide6 is available from the links above. The full licence text is at
https://www.gnu.org/licenses/lgpl-3.0.html.
