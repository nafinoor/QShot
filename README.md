# QShot

QShot — Screenshot & Annotation Tool
====================================

Small Qt-based screenshot and annotation tool inspired by Lightshot. Capture a screen region, annotate it (pen, rectangle, arrow, text, line), move recent annotations, zoom & pan, and upload to Imgur.

Features
--------

- Region selection for screenshots.
- Annotation tools: Pen, Rectangle, Arrow, Text, Line.
- Annotations stored as non-destructive layers (can be moved or undone).
- Multi-step undo/redo for annotation actions.
- Mouse-anchored zoom (Ctrl + mouse wheel) and pan (hold Space and drag).
- Copy/paste single annotation and copy final image to clipboard.
- Save to file and upload to Imgur (optional).

Installation
------------

### pip (recommended)

```bash
pip install .
```

For development:

```bash
pip install -e .
```

### System package (.deb)

```bash
sudo dpkg -i qshot_1.0.0_amd64.deb
sudo apt install -f
```

### Manual install

```bash
sudo ./install.sh
```

### From source (virtualenv)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 QShot.py
```

Quick start
-----------

After installing, run:

```bash
qshot
```

Or from source:

```bash
python3 QShot.py
```

Keyboard & mouse shortcuts (default)
-----------------------------------

- P: Pen tool
- R: Rectangle tool
- A: Arrow tool
- T: Text tool
- L: Line tool
- E: Select/Move tool
- Ctrl+Z: Undo
- Ctrl+Y / Ctrl+Shift+Z: Redo
- Delete: Delete selected annotation
- Ctrl+C: Copy selected annotation
- Ctrl+V: Paste copied annotation
- Ctrl+Shift+C: Copy final image to clipboard
- Ctrl+S: Save to file
- Ctrl+U: Upload to Imgur
- Ctrl + Mouse Wheel: Zoom in/out anchored at mouse pointer
- Space + Drag: Pan

Notes on Imgur upload
---------------------

The app uploads images to Imgur by default using an embedded client ID. You can override the client ID and enable a dry-run mode using environment variables:

- IMGUR_CLIENT_ID: set your Imgur client ID
- IMGUR_DRY_RUN=1: do not upload; save image to a temporary file and show a file:// URL

Example:

```bash
export IMGUR_CLIENT_ID="your-client-id"
export IMGUR_DRY_RUN=1
qshot
```

Troubleshooting
---------------

- If the app crashes on Ctrl+mouse-wheel, upgrade PyQt6 — the wheel handler uses Qt6's QWheelEvent.position().

- If you see painting-related errors (QPaintDevice...), the code uses copies and temporary previews to avoid painting directly onto widget-held QPixmaps.

Developer notes
--------------

- Main file: `QShot.py`
- Setup/installer: `setup.py`, `install.sh`, `debian/`
- Dependencies: `requirements.txt` (PyQt6, requests, Pillow)
- License: MIT
