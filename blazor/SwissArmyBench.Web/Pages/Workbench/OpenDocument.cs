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

    public string KindWord => IsNotebook ? "notebook" : "script";

    public string Title => Path is { } path
        ? System.IO.Path.GetFileName(path)
        : Untitled > 1 ? $"Untitled {KindWord} {Untitled}" : $"Untitled {KindWord}";

    /// <summary>The kind's word on its tab's icon (the classic tab kinds: Notebook, Script).</summary>
    public string KindLabel => IsNotebook ? "Notebook" : "Script";
}
