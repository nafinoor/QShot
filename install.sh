#!/bin/bash
set -e

DESTDIR="${DESTDIR:-}"
PREFIX="${PREFIX:-/usr/local}"
PYVER=$(python3 -c 'import sys; print(f"python{sys.version_info.major}.{sys.version_info.minor}")')
PYTHONDIR="$PREFIX/lib/$PYVER/dist-packages"

mkdir -p "$DESTDIR$PYTHONDIR"
install -m 644 QShot.py "$DESTDIR$PYTHONDIR/QShot.py"

# Install console script wrapper
install -d "$DESTDIR/$PREFIX/bin/"
cat > "$DESTDIR/$PREFIX/bin/qshot" << 'WRAPPER'
#!/usr/bin/env python3
import sys
from QShot import main
sys.exit(main())
WRAPPER
chmod 755 "$DESTDIR/$PREFIX/bin/qshot"

# Install desktop file
install -d "$DESTDIR/$PREFIX/share/applications/"
install -m 644 debian/qshot.desktop "$DESTDIR/$PREFIX/share/applications/com.github.you.qshot.desktop"

# Install icon
install -d "$DESTDIR/$PREFIX/share/pixmaps/"
install -m 644 debian/qshot.png "$DESTDIR/$PREFIX/share/pixmaps/qshot.png"

install -d "$DESTDIR/$PREFIX/share/icons/hicolor/256x256/apps/"
install -m 644 debian/qshot.png "$DESTDIR/$PREFIX/share/icons/hicolor/256x256/apps/qshot.png"

echo "Installed to $PREFIX"
echo "Run 'qshot' to start"
