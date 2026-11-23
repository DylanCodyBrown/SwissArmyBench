using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>
/// One open document of a Notebooks or Scripts page, a tab (the classic workbenchPage.ts Doc): its file, what was
/// opened, its text, whether it changed since, and its view once drawn. Each stays drawn while another tab is in
/// front, so its editors, cursor, outputs and unsaved text stay as they were.
/// </summary>
public sealed class OpenDocument
{
    public OpenDocument(int key, bool notebook)
    {
        Key = key;
        IsNotebook = notebook;
    }

    /// <summary>Its tab's key in the layout.</summary>
    public int Key { get; }

    public bool IsNotebook { get; }

    /// <summary>A blade's tab (its IDE): the blade's name; null for a notebook or a script.</summary>
    public string? Blade { get; set; }

    public bool IsBlade => Blade is not null;

    /// <summary>A structure's tab beside the code (a JSON, YAML, XML or TOML file).</summary>
    public bool IsStructure { get; init; }

    /// <summary>A structure tab's node to select as it opens ($.orders[3]).</summary>
    public string? StructureAt { get; init; }

    public StructureDoc? StructureDoc { get; set; }

    /// <summary>A workbook's design on the Excel canvas (the Accounting extension's; the classic tab kind workbook).</summary>
    public bool IsWorkbook { get; init; }

    /// <summary>A new workbook's title (the first sheet's heading), until it is saved.</summary>
    public string? WorkbookTitle { get; init; }

    public SwissArmyBench.Web.Pages.Accounting.WorkbookPage? WorkbookView { get; set; }

    /// <summary>A code app's file (the Power Apps extension's; the classic tab kind codefile): its path in the app.</summary>
    public string? CodeFile { get; init; }

    public CodeFileView? CodeFileView { get; set; }

    /// <summary>A notebook or a script: code that runs in the session (not a blade, structure or workbook).</summary>
    public bool IsCode => !IsBlade && !IsStructure && !IsWorkbook && CodeFile is null;

    /// <summary>A project's data.ipynb's view: cells, lineage or dictionary.</summary>
    public string DataView { get; set; } = "cells";

    /// <summary>data.ipynb's data dictionary's descriptions (kept in its metadata, saved with it).</summary>
    public System.Text.Json.JsonElement? Descriptions { get; set; }

    /// <summary>A notebook shown as a document (no code): Present.</summary>
    public bool Presenting { get; set; }

    /// <summary>A script's side panel shown beside it: its Run settings (API.py: its Endpoints).</summary>
    public bool RunSettingsOpen { get; set; }

    /// <summary>A project's data.ipynb: its Cells, Lineage and Dictionary views.</summary>
    public bool IsData => IsNotebook && Path is { } path && path.Replace('\\', '/').EndsWith("/data.ipynb", StringComparison.OrdinalIgnoreCase);

    /// <summary>Opened just made (New blade): its Properties open.</summary>
    public bool Fresh { get; init; }

    public SwissArmyBench.Web.Pages.Workbench.Blades.BladeIde? BladeIde { get; set; }

    /// <summary>Where it is saved (null until Save as).</summary>
    public string? Path { get; set; }

    /// <summary>The file's time when it was read or saved: a save over a newer file is refused.</summary>
    public double? Modified { get; set; }

    /// <summary>A notebook as opened (null: a new one).</summary>
    public OpenedNotebook? Notebook { get; set; }

    /// <summary>A script's text as the page knows it.</summary>
    public string ScriptText { get; set; } = string.Empty;

    public bool Dirty { get; set; }

    /// <summary>The file's text's hash when read or saved: a file_changed notice with the same one is this page's own.</summary>
    public string? Hash { get; set; }

    /// <summary>Its file changed elsewhere while it was edited here ("changed"), or went away ("gone"); else null.</summary>
    public string? Elsewhere { get; set; }

    /// <summary>Drawn again from the file (a notebook read again in place): its view's key.</summary>
    public int Version { get; set; }

    /// <summary>The number its new untitled kind gets ("Untitled notebook 2").</summary>
    public int Untitled { get; init; }

    public NotebookKept Kept { get; } = new();

    /// <summary>A script's console, kept with it.</summary>
    public CellModel Console { get; } = new();

    public NotebookView? NotebookView { get; set; }

    public ScriptView? ScriptView { get; set; }

    public string KindWord => IsWorkbook ? "workbook" : IsStructure ? "structure" : IsNotebook ? "notebook" : "script";

    public string Title => Blade ?? (CodeFile is { } file ? FilePaths.Name(file) : Path is { } path
        ? FilePaths.Name(path)
        : Untitled > 1 ? $"Untitled {KindWord} {Untitled}" : $"Untitled {KindWord}");

    /// <summary>The kind's word on its tab's icon (the classic tab kinds: Notebook, Script).</summary>
    public string KindLabel => IsBlade ? "Blade" : CodeFile is not null ? "Code file" : IsWorkbook ? "Workbook" : IsStructure ? "Structure" : IsNotebook ? "Notebook" : "Script";
}
