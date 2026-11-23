using System.Text.Json;
using System.Text.Json.Nodes;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

// A document's modes (the classic workbenchDocPanels.ts and workbenchDocModes.ts): a notebook's Cells | Present (the
// notebook as a document, no code), a project's data.ipynb's Cells | Lineage | Dictionary (its descriptions kept in
// data.ipynb, unsaved until Save), and a script's Run settings beside it; the palette's commands for them.
public partial class WorkbenchPage
{
    private const string NoData = "The document in front is not a project's data.ipynb";

    private IReadOnlyList<string> _vaults = [];

    private async Task LoadVaultsAsync()
    {
        try
        {
            _vaults = (await Workbench.BladesAsync()).Blades.Where(b => b.Connection == "vault").Select(b => b.Name).ToList();
        }
        catch (ApiException)
        {
            _vaults = []; // a variable comes from this computer or a plain value
        }
    }

    private Task SetDataViewAsync(OpenDocument doc, string view)
    {
        if (!doc.IsData)
        {
            throw new InvalidOperationException($"{NoData}.");
        }
        doc.DataView = view;
        return Task.CompletedTask;
    }

    private async Task OpenDictionaryAsync(OpenDocument doc)
    {
        await LoadOpenTablesAsync();
        await SetDataViewAsync(doc, "dictionary");
    }

    private Task PresentAsync(OpenDocument doc, bool? on = null)
    {
        doc.Presenting = on ?? !doc.Presenting;
        return Task.CompletedTask;
    }

    private Task ToggleRunSettingsAsync(OpenDocument doc)
    {
        doc.RunSettingsOpen = !doc.RunSettingsOpen;
        return Task.CompletedTask;
    }

    /// <summary>data.ipynb's tables (its read-only cells) and where each comes from (the open tables' origins).</summary>
    private IReadOnlyList<(string Name, string Source)> DictionaryTablesOf(OpenDocument doc) =>
        (doc.NotebookView?.TablesShown() ?? [])
            .Select(t => (t.Table, _openTables.FirstOrDefault(o => o.Name == t.Table)?.Origin ?? string.Empty))
            .ToList();

    private IReadOnlyList<TableInfo> _openTables = [];

    private async Task LoadOpenTablesAsync()
    {
        try
        {
            _openTables = (await Workbench.TablesAsync()).Tables;
        }
        catch (ApiException)
        {
            _openTables = [];
        }
    }

    /// <summary>A description typed in the Dictionary: kept in data.ipynb, unsaved until Save.</summary>
    private Task DescribeAsync(OpenDocument doc, (string Table, string? Column, string Text) said)
    {
        var all = JsonNode.Parse((doc.Descriptions ?? doc.Notebook?.Dictionary)?.GetRawText() ?? "{}") as JsonObject ?? [];
        var entry = all[said.Table] as JsonObject ?? new JsonObject { ["description"] = string.Empty, ["columns"] = new JsonObject() };
        all[said.Table] = entry;
        var columns = entry["columns"] as JsonObject ?? [];
        entry["columns"] = columns;
        var text = said.Text.Trim();
        if (said.Column is null)
        {
            entry["description"] = text;
        }
        else if (text.Length > 0)
        {
            columns[said.Column] = text;
        }
        else
        {
            columns.Remove(said.Column);
        }
        if ((entry["description"]?.GetValue<string>() ?? string.Empty).Length == 0 && columns.Count == 0)
        {
            all.Remove(said.Table);
        }
        doc.Descriptions = JsonSerializer.SerializeToElement(all);
        MarkDirty(doc);
        return Task.CompletedTask;
    }

    /// <summary>data.ipynb's Lineage: its last code cell traced back to the data (none: the view says Lineage).</summary>
    private int? DataLineageCell(OpenDocument doc) =>
        doc.NotebookView?.ToSave().Cells.LastOrDefault(c => c.Kind is "code" or "sql")?.Number;

    private Task DataLineageGoAsync(OpenDocument doc, LineageNode node)
    {
        doc.DataView = "cells";
        return GoToNodeAsync(node);
    }

    private List<WorkbenchCommand> ModeCommands()
    {
        var data = Front is { IsData: true } ? null : NoData;
        var notebook = Front?.NotebookView is null ? NoNotebook : null;
        return
        [
            new("data.view", "Data", "data.ipynb's view: Cells, Lineage or Dictionary", DataViewAskAsync, Disabled: data),
            new("dictionary.list", "Data", "The data dictionary: each table's columns, plain types, descriptions and where each comes from",
                () => Front is { } doc ? OpenDictionaryAsync(doc) : Task.CompletedTask, Disabled: data),
            new("dictionary.describe", "Data", "Describe a table or a column in the data dictionary (kept in data.ipynb, written into data.py)", DescribeAskAsync, Disabled: data),
            new("notebook.present", "Notebook", "Present: the notebook as a document (no code)", () => Front is { } doc ? PresentAsync(doc) : Task.CompletedTask, Disabled: notebook),
            new("script.runSettings", "Run", "Run settings: the script's arguments and variables", () => Front is { } doc ? ToggleRunSettingsAsync(doc) : Task.CompletedTask,
                Disabled: Front?.ScriptView is null ? "A script's command: put a script in front" : null),
        ];
    }

    private async Task DataViewAskAsync()
    {
        if (Front is { } doc && await Dialogs.AskTextAsync("data.ipynb's view", "cells, lineage or dictionary.", "View", doc.DataView, "Show") is { } typed
            && typed.Trim().ToLowerInvariant() is ("cells" or "lineage" or "dictionary") and var view)
        {
            await SetDataViewAsync(doc, view);
        }
    }

    private async Task DescribeAskAsync()
    {
        if (Front is not { } doc || await Dialogs.AskTextAsync("Describe", "The table, or table.column.", "Table", string.Empty, "Next") is not { Length: > 0 } named)
        {
            return;
        }
        if (await Dialogs.AskTextAsync("Describe", $"The description of {named}.", "Description", string.Empty, "Describe") is { } text)
        {
            var parts = named.Trim().Split('.', 2);
            await DescribeAsync(doc, (parts[0], parts.Length > 1 ? parts[1] : null, text));
        }
    }
}
