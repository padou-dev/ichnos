# Releasing Ichnos

A release is a git tag that packagers build from. Never release from an
untagged commit.

## 1. Prepare

1. Make sure the tests pass on Linux and Windows: `python -m pytest -v`.
2. Update the version in **all three** places:
   - `ichnos/__init__.py` (`__version__`)
   - `data/io.github.padou_dev.Ichnos.metainfo.xml` (add a `<release>` entry)
   - `packaging/arch/PKGBUILD` (`pkgver`, and set `pkgrel=1`)
3. Add the changes to `CHANGELOG.md`.
4. Commit: `git commit -am "Release 0.2.0"`.

## 2. Tag and push

```
git tag -a v0.2.0 -m "Ichnos 0.2.0"
git push
git push origin v0.2.0
```

On GitHub, open **Releases → Draft a new release**, choose the tag, and paste
the changelog entry.

## 3. Update the AUR package (Arch Linux)

The AUR package lives in its own git repository, separate from this one.

First time only:

1. Create an account on <https://aur.archlinux.org> and add your SSH key.
2. `git clone ssh://aur@aur.archlinux.org/ichnos.git aur-ichnos`

Every release:

```
cp packaging/arch/PKGBUILD ../aur-ichnos/
cd ../aur-ichnos
updpkgsums                 # replaces 'SKIP' with the real checksum
makepkg -si                # build, run the tests, install locally
makepkg --printsrcinfo > .SRCINFO
git add PKGBUILD .SRCINFO
git commit -m "Update to 0.2.0"
git push
```

Copy the updated checksum back into `packaging/arch/PKGBUILD` here too.

`updpkgsums` comes from the `pacman-contrib` package.

## 4. Check the desktop files (Linux)

```
desktop-file-validate data/io.github.padou_dev.Ichnos.desktop
appstreamcli validate data/io.github.padou_dev.Ichnos.metainfo.xml
```
