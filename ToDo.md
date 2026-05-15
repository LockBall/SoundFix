# ToDo

## 1. GUI Responsiveness

- [ ] Move peak analysis off the Tkinter UI thread.
- [ ] Move batch conversion off the Tkinter UI thread.
- [ ] Keep UI controls responsive while ffmpeg work is running.
- [ ] Add a progress bar so the GUI clearly indicates background work is active.
- [ ] Update progress text per file during batch conversion.

## 2. Conversion Safety

- [ ] Add a pre-run summary showing file count, output folder, first gain, interval, and encoder mode.
- [ ] Make stale settings obvious after changing input file, headroom, interval, or output folder.

## 3. Test Coverage

- [ ] Test that the default encoder mode uses Vorbis quality.
- [ ] Test `gain_to_peak_headroom_db()` with positive and negative raw peaks.
- [ ] Test that peak analysis ignores channel peaks and uses the `Overall` peak.

## 4. Local Workspace Health

- [ ] Investigate why `compileall` cannot write to existing `__pycache__` folders.
- [ ] Remove or repair locked/generated cache folders if they are not needed.

## 5. GUI Code Organization

- [ ] Split `app.py` into smaller modules when the next behavior change makes it worthwhile.
- [ ] Consider separate modules for formatting helpers, widget builders, and event handlers.

