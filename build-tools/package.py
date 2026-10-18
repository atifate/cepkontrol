"""Bundle executable, quick start and dependency license notices."""
from importlib import metadata
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent.parent
dist = root / 'dist'
names = ['Pillow', 'mss', 'PyAutoGUI', 'cryptography', 'websocket-client', 'cffi',
         'pycparser', 'PyMsgBox', 'PyTweening', 'PyScreeze', 'PyGetWindow',
         'PyRect', 'MouseInfo', 'pyperclip', 'pyinstaller', 'altgraph', 'qrcode', 'colorama', 'pystray', 'six']
notices = []
for name in names:
    package = metadata.distribution(name)
    notices.append(f'\n{"=" * 70}\n{name} {package.version}\n')
    for file in package.files or []:
        if any(word in file.name.lower() for word in ('license', 'copying')) and '.dist-info' in str(file):
            path = Path(package.locate_file(file))
            if path.is_file():
                notices.append(path.read_text(encoding='utf-8', errors='replace'))
(dist / 'UCUNCU-TARAF-LISANSLARI.txt').write_text('\n'.join(notices), encoding='utf-8')
with zipfile.ZipFile(dist / 'CepKontrol-Windows.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in [dist / 'CepKontrol.exe', root / 'HIZLI-BASLA.txt', root / 'LICENSE', dist / 'UCUNCU-TARAF-LISANSLARI.txt']:
        archive.write(path, arcname=path.name)
print('Windows package created.')
