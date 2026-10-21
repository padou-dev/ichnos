# Ichnos

**View, edit and remove photo metadata, safely.**

Photos carry traces of where, when and with what they were taken: GPS
coordinates, your name, your camera's serial number, sometimes a thumbnail of
the photo before you cropped it. *Ichnos* (ίχνος, Greek for *trace*) shows you
every one of those traces and removes the ones you choose.

> **Status:** early development (0.1.0). Feedback and bug reports are welcome.

## Features

- **See everything**, grouped by where it lives: EXIF, GPS, XMP, IPTC, maker
  notes, PNG text. File-system details are kept apart, because they are not in
  the image at all.
- **Presets**
  - *Location only*: GPS and place names
  - *Share-safe*: location, personal details, serial numbers, thumbnails, maker
    notes and edit history. Date, camera and exposure details stay.
  - *Strip all*: everything that isn't needed to display the image
- **Fine control**: tick or untick any individual tag, and edit artist,
  copyright, dates and descriptions.
- **Folders and batches**: open many files at once and clean them in one go.
- **Safe by design**
  - Originals are never modified; cleaned copies are written next to them as
    `name_clean.jpg`.
  - Existing files are never overwritten.
  - Every copy is read back and checked; anything that couldn't be removed is
    reported, never silently ignored.
  - Orientation, colour profiles and image structure are always kept, so
    photos still look right.
- **Command line** for scripts: `ichnos strip --preset share-safe *.jpg`
- **Omarchy theme support**: on [Omarchy](https://omarchy.org), Ichnos uses the
  active theme's colours and follows theme changes live.
- Works on **Linux** and **Windows**.

## Installing

### Requirements

- Python 3.11 or newer
- [PySide6](https://pypi.org/project/PySide6/) (Qt for Python)
- [exiftool](https://exiftool.org) by Phil Harvey

### Arch Linux

```
sudo pacman -S --needed pyside6 perl-image-exiftool
```

An AUR package is planned. Until then, run from source (below).

### Windows

Install [Python](https://www.python.org) and exiftool (for example
`winget search exiftool`), then run from source.

### Running from source

```
git clone https://github.com/padou-dev/ichnos.git
cd ichnos
python -m ichnos
```

On Windows, create a virtual environment first and install PySide6 into it:

```
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install PySide6 pytest
python -m ichnos
```

## Using the command line

```
ichnos                                  open the app
ichnos photo.jpg ~/Pictures/trip        open files and folders in the app
ichnos show photo.jpg                   list a photo's metadata
ichnos strip --dry-run photo.jpg        see what would be removed
ichnos strip photo.jpg                  write photo_clean.jpg (share-safe)
ichnos strip -p location -o out/ *.jpg  remove only location, write into out/
ichnos presets                          describe the presets
```

Run from source with `python -m ichnos` in place of `ichnos`. See
`ichnos --help` or `man ichnos` for everything.

## Keyboard shortcuts

| Keys | Action |
|---|---|
| Ctrl+O / Ctrl+Shift+O | Open files / folder |
| Space | Tick or untick the selected tag |
| F2 | Edit the selected tag |
| Ctrl+1 / 2 / 3 | Location only / Share-safe / Strip all |
| Ctrl+F | Filter tags |
| Ctrl+R | Review changes |
| Ctrl+Enter | Write copies |
| Delete | Remove the selected files from the list |

## Running the tests

```
python -m pytest -v
```

The window tests run without opening anything on screen.

## How it works

Ichnos is a Python + Qt (PySide6) front end for exiftool. The core
(`ichnos/metadata.py`, `presets.py`, `writer.py`) knows nothing about the user
interface, which is why the command line and the app behave identically.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
