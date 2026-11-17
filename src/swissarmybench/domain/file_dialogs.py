# ruff: noqa: E501  (the PowerShell, C# and AppleScript texts keep their own long lines)
"""The system's own file dialog, opened by the server on the user's click (the owner, 2026-11-17: "the file
picker for the entire app is terrible"), and the page's own picker's rules (its fallback). Text only: what is
asked for (a request, checked), which tool each system uses, each tool's command line or script (the values
never inside a script's text: an argument, an environment variable), its answer read, and dialogs.json's
recent folders per kind of pick. server/dialog_runner.py runs the plan; nothing here starts anything.

  Windows   Tk (its tk_getOpenFile, tk_getSaveFile and tk_chooseDirectory are the modern IFileDialog since
            Tk 8.6), else PowerShell: Windows Forms' Open and Save dialogs and IFileOpenDialog with
            FOS_PICKFOLDERS for a folder (not the old tree of FolderBrowserDialog)
  macOS     osascript's choose file, choose folder and choose file name (NSOpenPanel, NSSavePanel),
            activated first so it comes to the front; else Tk (also NSOpenPanel on the Mac)
  Linux     kdialog on KDE, zenity, kdialog, else Tk; nothing without a display (DISPLAY, WAYLAND_DISPLAY)
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

MODES: tuple[str, ...] = ("file", "folder", "save")
TOOLS: tuple[str, ...] = ("tk", "powershell", "osascript", "zenity", "kdialog")
# Long enough for a person to find their file; the dialog's process is ended after it.
TIME_LIMIT_SECONDS: int = 600
# The switch that turns system dialogs off (a test's server, a machine where they misbehave).
OFF_VARIABLE: str = "SWISSARMYBENCH_SYSTEM_DIALOGS"
RECENT_PER_KIND: int = 8
MAX_KINDS: int = 40
_SUFFIX = re.compile(r"^\.[A-Za-z0-9_+-]{1,11}$")
_KIND = re.compile(r"^[a-z0-9][a-z0-9.,:_-]{0,79}$")
_MAX_SUFFIXES = 20
_MAX_TEXT = 200
_MAX_PATH = 4096


class DialogFailed(Exception):
    """The dialog's process ended without an answer (not a cancel): the page falls back to its own."""


@dataclass(frozen=True)
class DialogRequest:
    mode: str
    title: str
    start: str | None
    suffixes: tuple[str, ...]
    name: str | None
    kind: str


@dataclass(frozen=True)
class Plan:
    """One dialog's process: its command line, the environment it adds, and how its answer is read."""

    tool: str
    argv: tuple[str, ...]
    env: Mapping[str, str]
    cancel_codes: frozenset[int]


def _text(value: Any, field: str, limit: int) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} is text.")
    if len(value) > limit or "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError(f"{field} is one line of at most {limit} characters.")
    return value


def kind_of(mode: str, suffixes: tuple[str, ...]) -> str:
    """The kind of pick a caller made when it named none: its mode and file kinds ("file:.csv,.xlsx")."""
    return f"{mode}:{','.join(sorted(suffixes))}" if suffixes else mode


def read_request(body: Any) -> DialogRequest:
    """POST /dialogs/choose's body, checked: {mode, title, start?, suffixes?, name?, kind?}."""
    if not isinstance(body, dict):
        raise ValueError("Send {mode, title, start?, suffixes?, name?}.")
    mode = body.get("mode", "file")
    if mode not in MODES:
        raise ValueError("mode is file, folder or save.")
    title = _text(body.get("title"), "title", _MAX_TEXT) or "Choose"
    start = _text(body.get("start"), "start", _MAX_PATH)
    name = _text(body.get("name"), "name", 255) if mode == "save" else None
    if name and re.search(r"[\\/]", name):
        raise ValueError("name is a file name, without a folder.")
    raw = body.get("suffixes") or []
    if not isinstance(raw, list) or len(raw) > _MAX_SUFFIXES:
        raise ValueError('suffixes is a list of at most 20, as [".csv", ".xlsx"].')
    suffixes: list[str] = []
    for suffix in raw:
        if not isinstance(suffix, str) or not _SUFFIX.match(suffix):
            raise ValueError("Name each file kind as .csv (a dot, then letters or digits).")
        if suffix.lower() not in suffixes:
            suffixes.append(suffix.lower())
    found = tuple(suffixes) if mode != "folder" else ()
    kind = body.get("kind") or kind_of(mode, found)
    if not isinstance(kind, str) or not _KIND.match(kind):
        raise ValueError("kind is a short name of lower-case letters, digits and .,:_-")
    return DialogRequest(mode, title, start, found, name, kind)


# ===== which tool =====


def choose_tool(
    platform: str,
    env: Mapping[str, str],
    have: Callable[[str], bool],
    tk: Callable[[], bool],
) -> tuple[str | None, str]:
    """The tool this computer's dialogs open with, and why none when none: (tool, reason). `have` says
    whether a command is on the PATH; `tk` whether this Python's Tk works (asked last: it starts a process)."""
    if env.get(OFF_VARIABLE, "").strip().lower() in ("0", "off", "false", "no"):
        return None, "System file dialogs are turned off here."
    if platform == "win32":
        if tk():
            return "tk", ""
        if have("powershell"):
            return "powershell", ""
        return None, "Neither Tk nor PowerShell is here."
    if platform == "darwin":
        if have("osascript"):
            return "osascript", ""
        return ("tk", "") if tk() else (None, "Neither osascript nor Tk is here.")
    if not (env.get("DISPLAY") or env.get("WAYLAND_DISPLAY")):
        return None, "No display: this server has no desktop to open a dialog on."
    kde = "kde" in env.get("XDG_CURRENT_DESKTOP", "").lower()
    if kde and have("kdialog"):
        return "kdialog", ""
    for command in ("zenity", "kdialog"):
        if have(command):
            return command, ""
    if tk():
        return "tk", ""
    return None, "No zenity, kdialog or Tk here."


# ===== each tool's plan =====


def filter_label(suffixes: tuple[str, ...]) -> str:
    return f"Files ({', '.join(suffixes)})"


def _join(folder: str, name: str) -> str:
    sep = "\\" if "\\" in folder and "/" not in folder else "/"
    return folder.rstrip("\\/") + sep + name


TK_SCRIPT = r"""
import json, os, sys
r = json.loads(sys.argv[1])
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
import tkinter
from tkinter import filedialog
root = tkinter.Tk()
root.withdraw()
try:
    root.attributes("-topmost", True)
except Exception:
    pass
root.update_idletasks()
root.lift()
root.focus_force()
options = {"parent": root, "title": r["title"]}
if r["folder"]:
    options["initialdir"] = r["folder"]
types = [tuple(t) for t in r["types"]]
if r["mode"] == "folder":
    path = filedialog.askdirectory(mustexist=True, **options)
elif r["mode"] == "save":
    path = filedialog.asksaveasfilename(initialfile=r["name"] or "", filetypes=types, **options)
else:
    path = filedialog.askopenfilename(filetypes=types, **options)
root.destroy()
if isinstance(path, tuple):
    path = path[0] if path else ""
if path and sys.platform == "win32":
    path = os.path.normpath(path)
sys.stdout.write(json.dumps({"path": path} if path else {"cancelled": True}))
"""

# PowerShell: the values arrive in SAB_DIALOG (JSON), never in the script's text. A hidden, topmost form owns
# the dialog, so it opens in front of the browser.
_FOLDER_CS = r"""
using System;
using System.Runtime.InteropServices;
public static class SabFolderPicker {
  [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")] class FileOpenDialogRcw {}
  [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IFileDialog {
    [PreserveSig] int Show(IntPtr parent);
    void SetFileTypes(uint count, IntPtr specs);
    void SetFileTypeIndex(uint index);
    void GetFileTypeIndex(out uint index);
    void Advise(IntPtr events, out uint cookie);
    void Unadvise(uint cookie);
    void SetOptions(uint options);
    void GetOptions(out uint options);
    void SetDefaultFolder(IShellItem item);
    void SetFolder(IShellItem item);
    void GetFolder(out IShellItem item);
    void GetCurrentSelection(out IShellItem item);
    void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
    void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string name);
    void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
    void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
    void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
    void GetResult(out IShellItem item);
  }
  [ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IShellItem {
    void BindToHandler(IntPtr bc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
    void GetParent(out IShellItem parent);
    void GetDisplayName(uint sigdn, [MarshalAs(UnmanagedType.LPWStr)] out string name);
    void GetAttributes(uint mask, out uint attributes);
    void Compare(IShellItem other, uint hint, out int order);
  }
  [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
  static extern void SHCreateItemFromParsingName(string path, IntPtr bc, [MarshalAs(UnmanagedType.LPStruct)] Guid riid, out IShellItem item);
  public static string Pick(IntPtr owner, string title, string folder) {
    IFileDialog dialog = (IFileDialog)new FileOpenDialogRcw();
    uint options;
    dialog.GetOptions(out options);
    dialog.SetOptions(options | 0x20 | 0x40 | 0x800);
    if (!String.IsNullOrEmpty(title)) dialog.SetTitle(title);
    if (!String.IsNullOrEmpty(folder)) {
      try { IShellItem start; SHCreateItemFromParsingName(folder, IntPtr.Zero, typeof(IShellItem).GUID, out start); dialog.SetFolder(start); } catch (Exception) {}
    }
    if (dialog.Show(owner) != 0) return null;
    IShellItem item;
    dialog.GetResult(out item);
    string path;
    item.GetDisplayName(0x80058000, out path);
    return path;
  }
}
"""

POWERSHELL_SCRIPT = (
    r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$r = $env:SAB_DIALOG | ConvertFrom-Json
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()
$owner = New-Object System.Windows.Forms.Form
$owner.TopMost = $true
$owner.ShowInTaskbar = $false
$owner.FormBorderStyle = 'None'
$owner.Opacity = 0
$owner.StartPosition = 'CenterScreen'
$owner.Size = New-Object System.Drawing.Size(1, 1)
$owner.Show()
$owner.Activate()
$path = $null
if ($r.mode -eq 'folder') {
  Add-Type -TypeDefinition @'
"""
    + _FOLDER_CS
    + r"""
'@
  $path = [SabFolderPicker]::Pick($owner.Handle, $r.title, $r.folder)
} else {
  if ($r.mode -eq 'save') {
    $d = New-Object System.Windows.Forms.SaveFileDialog
    $d.OverwritePrompt = $true
    if ($r.name) { $d.FileName = $r.name }
  } else {
    $d = New-Object System.Windows.Forms.OpenFileDialog
    $d.CheckFileExists = $true
  }
  $d.Title = $r.title
  if ($r.folder) { $d.InitialDirectory = $r.folder }
  if ($r.filter) { $d.Filter = $r.filter }
  if ($d.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) { $path = $d.FileName }
}
$owner.Close()
if ($path) { [Console]::Out.Write((@{ path = $path } | ConvertTo-Json -Compress)) }
else { [Console]::Out.Write('{"cancelled":true}') }
"""
)

# osascript: the values are the run handler's arguments (title, folder, name, then the file kinds).
OSASCRIPT = r"""
on run argv
  set theTitle to item 1 of argv
  set theFolder to item 2 of argv
  set theName to item 3 of argv
  set theMode to item 4 of argv
  set theTypes to {}
  if (count of argv) > 4 then set theTypes to items 5 thru -1 of argv
  activate
  try
    if theMode is "folder" then
      if theFolder is "" then
        set chosen to choose folder with prompt theTitle
      else
        set chosen to choose folder with prompt theTitle default location (POSIX file theFolder)
      end if
    else if theMode is "save" then
      if theFolder is "" then
        set chosen to choose file name with prompt theTitle default name theName
      else
        set chosen to choose file name with prompt theTitle default name theName default location (POSIX file theFolder)
      end if
    else
      if theFolder is "" and theTypes is {} then
        set chosen to choose file with prompt theTitle
      else if theFolder is "" then
        set chosen to choose file with prompt theTitle of type theTypes
      else if theTypes is {} then
        set chosen to choose file with prompt theTitle default location (POSIX file theFolder)
      else
        set chosen to choose file with prompt theTitle of type theTypes default location (POSIX file theFolder)
      end if
    end if
  on error number -128
    return ""
  end try
  return POSIX path of chosen
end run
"""


def plan(tool: str, request: DialogRequest, folder: str | None, python: str) -> Plan:
    """The command line for `tool`. `folder` is the existing folder to start in (None: the tool's own
    choice); `python` the Python whose Tk opens the dialog (the server's own)."""
    mode, title, suffixes = request.mode, request.title, request.suffixes
    name = request.name or ""
    if tool == "tk":
        types: list[list[str]] = []
        if suffixes:
            types.append([filter_label(suffixes), " ".join(f"*{s}" for s in suffixes)])
        types.append(["All files", "*"])
        payload = {"mode": mode, "title": title, "folder": folder, "name": name, "types": types}
        return Plan(
            tool,
            (python, "-I", "-c", TK_SCRIPT, json.dumps(payload)),
            {"PYTHONIOENCODING": "utf-8"},
            frozenset(),
        )
    if tool == "powershell":
        filter_text = ""
        if mode != "folder":
            parts = [f"{filter_label(suffixes)}|{';'.join(f'*{s}' for s in suffixes)}"] if suffixes else []
            filter_text = "|".join([*parts, "All files|*.*"])
        payload = {"mode": mode, "title": title, "folder": folder or "", "name": name, "filter": filter_text}
        encoded = base64.b64encode(POWERSHELL_SCRIPT.encode("utf-16-le")).decode("ascii")
        return Plan(
            tool,
            (
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-STA",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ),
            {"SAB_DIALOG": json.dumps(payload)},
            frozenset(),
        )
    if tool == "osascript":
        kinds = [s.lstrip(".") for s in suffixes] if mode == "file" else []
        return Plan(
            tool,
            ("osascript", "-e", OSASCRIPT, title, folder or "", name, mode, *kinds),
            {},
            frozenset(),
        )
    if tool == "zenity":
        argv = ["zenity", "--file-selection", f"--title={title}"]
        if mode == "folder":
            argv.append("--directory")
        if mode == "save":
            argv += ["--save", "--confirm-overwrite"]
        if folder:
            argv.append(f"--filename={_join(folder, name) if mode == 'save' else _join(folder, '')}")
        elif mode == "save" and name:
            argv.append(f"--filename={name}")
        if suffixes and mode != "folder":
            patterns = " ".join(p for s in suffixes for p in (f"*{s}", f"*{s.upper()}"))
            argv += [f"--file-filter={filter_label(suffixes)} | {patterns}", "--file-filter=All files | *"]
        return Plan(tool, tuple(argv), {}, frozenset({1}))
    if tool == "kdialog":
        where = folder or "."
        filter_text = ""
        if suffixes and mode != "folder":
            patterns = " ".join(p for s in suffixes for p in (f"*{s}", f"*{s.upper()}"))
            filter_text = f"{patterns}|{filter_label(suffixes)}\n*|All files"
        if mode == "folder":
            argv = ["kdialog", "--title", title, "--getexistingdirectory", where]
        elif mode == "save":
            argv = ["kdialog", "--title", title, "--getsavefilename", _join(where, name) if name else where]
        else:
            argv = ["kdialog", "--title", title, "--getopenfilename", where]
        if filter_text:
            argv.append(filter_text)
        return Plan(tool, tuple(argv), {}, frozenset({1}))
    raise ValueError(f"No such dialog tool: {tool}.")


def read_answer(chosen: Plan, code: int, stdout: str, stderr: str) -> dict[str, Any]:
    """{"path"} or {"cancelled": true}; DialogFailed for anything else (the page falls back)."""
    if code in chosen.cancel_codes:
        return {"cancelled": True}
    if code != 0:
        last = (stderr.strip().splitlines() or ["no message"])[-1][:200]
        raise DialogFailed(f"The {chosen.tool} dialog ended with code {code}: {last}")
    if chosen.tool in ("tk", "powershell"):
        try:
            answer = json.loads(stdout.strip() or "{}")
        except ValueError:
            raise DialogFailed(f"The {chosen.tool} dialog's answer could not be read.") from None
        path = answer.get("path") if isinstance(answer, dict) else None
        return {"path": path} if isinstance(path, str) and path else {"cancelled": True}
    path = stdout.rstrip("\r\n")
    return {"path": path} if path else {"cancelled": True}


# ===== recent folders, per kind of pick (dialogs.json) =====


def folder_of(path: str, mode: str) -> str:
    """The folder a pick was made in: the folder itself, or a file's folder."""
    if mode == "folder":
        return path
    trimmed = path.rstrip("\\/")
    cut = max(trimmed.rfind("/"), trimmed.rfind("\\"))
    if cut <= 0:
        return trimmed[:1] if cut == 0 else trimmed
    folder = trimmed[:cut]
    return folder + "\\" if re.fullmatch(r"[A-Za-z]:", folder) else folder


def recent(data: Any, kind: str) -> list[str]:
    """dialogs.json's recent folders for one kind of pick, newest first."""
    found = (data or {}).get("recent", {}) if isinstance(data, dict) else {}
    folders = found.get(kind) if isinstance(found, dict) else None
    return [f for f in folders if isinstance(f, str)] if isinstance(folders, list) else []


def remember(data: Any, kind: str, folder: str) -> dict[str, Any]:
    """dialogs.json with `folder` first in `kind`'s list (at most eight; the oldest kind dropped past 40).
    Paths only."""
    if not _KIND.match(kind):
        raise ValueError("kind is a short name of lower-case letters, digits and .,:_-")
    if not folder or len(folder) > _MAX_PATH or "\x00" in folder:
        raise ValueError("folder is a path.")
    old = data.get("recent", {}) if isinstance(data, dict) else {}
    kinds = {k: recent(data, k) for k in old} if isinstance(old, dict) else {}
    mine = [folder, *[f for f in kinds.pop(kind, []) if f != folder]][:RECENT_PER_KIND]
    kept = list(kinds.items())[: MAX_KINDS - 1]
    return {"recent": {kind: mine, **dict(kept)}}


# ===== the page's own picker: a new folder's name =====

_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?$", re.IGNORECASE)


def check_folder_name(name: Any) -> str:
    """New folder's name: one name, no slashes or the characters Windows refuses, not . or .."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Type the new folder's name.")
    found: str = name.strip()
    if len(found) > 255 or found in (".", "..") or re.search(r'[\\/:*?"<>|\x00-\x1f]', found):
        raise ValueError('A folder name has no \\ / : * ? " < > | and is not . or ..')
    if _RESERVED.match(found) or found.endswith("."):
        raise ValueError(f"{found} is a name Windows keeps for itself.")
    return found
