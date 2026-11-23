using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Pages.Accounting;

/// <summary>The Excel canvas's top row (the classic excelCanvas.ts drawTop): Edit and Play, Undo and Redo, the Blocks
/// and Templates menus, Export workbook.py, Download and Save; the sheets' tabs; the page's keys.</summary>
public partial class WorkbookPage
{
    private const string Ending = ".design.json";

    private async Task<IJSObjectReference> ModuleAsync() =>
        _module ??= await Js.InvokeAsync<IJSObjectReference>("import", "./js/workbook.js");

    /// <summary>Play: the workbook built from the open tables and each sheet shown as built (the palette's too).</summary>
    public async Task PlayAsync()
    {
        if (_building || _state is null)
        {
            return;
        }
        _building = true;
        _error = null;
        StateHasChanged();
        try
        {
            await CallAsync(HttpMethod.Post, "/play");
            _playing = true;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _building = false;
    }

    /// <summary>Edit the blocks again (the palette's Edit the workbook's blocks).</summary>
    public void Edit()
    {
        _playing = false;
        StateHasChanged();
    }

    /// <summary>The workbook as it stands, in words (the palette's report): its sheets and their blocks.</summary>
    public string Report() => _state is not { } state
        ? "The workbook is still opening."
        : string.Join('\n', state.Design.Sheets.Select(s => $"{s.Name}: {(s.Blocks.Count == 0 ? "no blocks" : string.Join(", ", s.Blocks.Select(b => b.Kind)))}"))
            + (_playing ? "\nPlayed." : string.Empty) + (state.Unsaved ? "\nUnsaved changes." : string.Empty);

    private async Task AddBlockAsync(string kind)
    {
        if (Sheet is not { } sheet || _state is not { } state)
        {
            return;
        }
        var first = state.Tables.FirstOrDefault() ?? _openTables.FirstOrDefault() ?? string.Empty;
        var body = new Dictionary<string, object?> { ["kind"] = kind };
        switch (kind)
        {
            case "title":
                body["text"] = state.Design.Title.Length > 0 ? state.Design.Title : "Title";
                break;
            case "text":
                body["text"] = string.Empty;
                break;
            case "chart":
                body["chart"] = "column";
                body["from"] = (sheet.Blocks.FirstOrDefault(b => b.Kind == "pivot") ?? sheet.Blocks.FirstOrDefault(b => b.Kind == "table"))?.Id ?? string.Empty;
                break;
            case "pivot":
                body["source"] = new { table = first };
                body["rows"] = Array.Empty<string>();
                body["columns"] = Array.Empty<string>();
                body["values"] = new[] { new { agg = "count" } };
                break;
            default:
                body["source"] = new { table = first };
                break;
        }
        if (await ChangeAsync(HttpMethod.Post, $"/sheets/{Uri.EscapeDataString(sheet.Id)}/blocks", body) is { Block: { } made })
        {
            await SelectAsync(made);
            StateHasChanged();
        }
    }

    private async Task BlocksMenuAsync()
    {
        var at = await (await ModuleAsync()).InvokeAsync<ScreenPoint>("below", _blocksButton);
        _menu = new WorkbookMenu("Blocks", at.X, at.Y, WorkbookRules.Kinds.Select(k => new MenuEntry(WorkbookRules.Word(k), WorkbookRules.IconOf(k), () => AddBlockAsync(k))).ToList());
    }

    private async Task TemplatesMenuAsync()
    {
        var at = await (await ModuleAsync()).InvokeAsync<ScreenPoint>("below", _templatesButton);
        _menu = new WorkbookMenu("Templates and statements", at.X, at.Y,
        [
            new("Templates…", "excel", () => SetAsync(() => _templatesOpen = true)),
            new("Statements and invoices…", "copy", () => SetAsync(() => OpenStatements(null))),
        ]);
    }

    // A menu's line runs in the menu: the page draws itself again after it.
    private Task SetAsync(Action change)
    {
        change();
        StateHasChanged();
        return Task.CompletedTask;
    }

    private void OpenStatements(string? template)
    {
        _templatesOpen = false;
        _statementsFor = template;
        _statementsOpen = true;
    }

    private async Task DownloadAsync()
    {
        if (_state is not { } state)
        {
            return;
        }
        try
        {
            var (bytes, name) = await Accounting.DownloadAsync(state.Id);
            var file = name ?? $"{(state.Design.Title.Length > 0 ? state.Design.Title : "workbook")}.xlsx";
            await using var files = await Js.InvokeAsync<IJSObjectReference>("import", "./js/files.js");
            await files.InvokeVoidAsync("save", file, bytes);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Save (a new design asks where: the system's dialog, else the path typed).</summary>
    public async Task<bool> SaveAsync(bool asNew = false)
    {
        if (_state is not { } state)
        {
            return false;
        }
        var where = asNew ? null : state.Path;
        if (where is null)
        {
            var chosen = await Files.ChooseAsync("save", asNew ? "Save workbook design as" : "Save workbook design", state.Path, "workbook", name: $"workbook{Ending}");
            if (string.IsNullOrWhiteSpace(chosen))
            {
                return false;
            }
            where = chosen.EndsWith(".json", StringComparison.OrdinalIgnoreCase) ? chosen : chosen + Ending;
        }
        try
        {
            var done = await CallAsync(HttpMethod.Post, "/save", new { path = where });
            _opened = done.Path ?? where;
            await OnSaved.InvokeAsync(_opened);
            _ = Notes.SayAsync($"Saved {System.IO.Path.GetFileName(_opened)}");
            return true;
        }
        catch (ApiException error)
        {
            _error = error;
            return false;
        }
    }

    private async Task ExportAsync()
    {
        if (_state?.Path is null && !await SaveAsync())
        {
            return;
        }
        try
        {
            var done = await Accounting.ExportAsync(_state!.Id);
            _ = Notes.SayAsync($"{done.Path}: {done.Run}");
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task SelectSheetAsync(string id)
    {
        _sheetId = id;
        await SelectAsync(null);
    }

    private async Task AddSheetAsync()
    {
        if (await ChangeAsync(HttpMethod.Post, "/sheets", new { }) is { Sheet: { } made })
        {
            _sheetId = made;
            _selected = null;
        }
    }

    private Task RenameSheetAsync((string Id, string Name) renamed) =>
        SheetAsync(renamed.Id, new Dictionary<string, object?> { ["name"] = renamed.Name });

    private Task RemoveSheetAsync(string id) => ChangeAsync(HttpMethod.Delete, $"/sheets/{Uri.EscapeDataString(id)}");

    /// <summary>The page's keys outside a box: Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y, Ctrl+S, Escape (nothing selected).</summary>
    private async Task KeyAsync(KeyboardEventArgs e)
    {
        var command = e.CtrlKey || e.MetaKey;
        if (command && !e.AltKey && e.Key.Equals("z", StringComparison.OrdinalIgnoreCase))
        {
            await (e.ShiftKey ? RedoAsync() : UndoAsync());
        }
        else if (command && e.Key.Equals("y", StringComparison.OrdinalIgnoreCase))
        {
            await RedoAsync();
        }
        else if (command && e.Key.Equals("s", StringComparison.OrdinalIgnoreCase))
        {
            await SaveAsync();
        }
        else if (e.Key == "Escape" && _selected is not null)
        {
            _selected = null;
        }
    }

    private IReadOnlyList<string> Notices =>
    [
        .. _state?.Problem is { } problem ? [problem] : Array.Empty<string>(),
        .. _state?.Missing is { Count: > 0 } missing ? [$"Not open: {string.Join(", ", missing)}"] : Array.Empty<string>(),
        .. _state?.Problems ?? [],
    ];

    /// <summary>A design's file as its name: workbook.design.json is "workbook".</summary>
    public static string NameOf(string path)
    {
        var name = System.IO.Path.GetFileName(path);
        return name.EndsWith(Ending, StringComparison.OrdinalIgnoreCase) ? name[..^Ending.Length] : name;
    }
}
