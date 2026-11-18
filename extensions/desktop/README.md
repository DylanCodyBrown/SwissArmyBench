# Swiss Army Bench: Desktop

Swiss Army Bench in app windows of its own instead of browser tabs. The pages are the same ones the browser
shows; only the windows around them change.

- Installed from the app's Extensions page (one click). The app then opens in its own windows: the launch,
  `swissarmybench open`, the tray's Open and `swissarmybench desktop`. Remove it and the app opens in the
  browser again.
- Each page is a window with Qt WebEngine (Chromium). Pop-outs, the Workbench and panel windows open as app
  windows too, and each kind of window remembers its size and place. Addresses that are not the app's own
  open in your browser.
- Downloads ask where to save with the system's dialog, then offer Show in folder. Print to PDF saves a PDF.
- One tray icon (Start at sign-in, Update, Quit), the same menu as before.
- Keys: F12 developer tools, F11 full screen, Alt+Left and Alt+Right back and forward, F5 reload,
  Ctrl+P print to PDF, Ctrl+W close the window.

It needs Qt for Python with Qt WebEngine (`PySide6-Essentials`, `PySide6-Addons`, `PySide6-WebEngine`
6.12.0, LGPLv3), about 670 MB installed. Its cookies, local storage and cache are kept in the app's state
folder (`desktop/profile`).
