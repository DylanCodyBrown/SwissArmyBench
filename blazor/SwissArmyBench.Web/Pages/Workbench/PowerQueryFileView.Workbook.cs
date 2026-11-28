using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Pages.Workbench;

// A Power Query file linked to an Excel workbook (the owner, 2026-11-28: "Excel's own Power Query"): its first line
// names the workbook (`// workbook: Sales Report.xlsx`). The view asks the server what the link is (the workbook by
// name, there or not, open in Excel, its queries changed on disk), and after the page saved the file it writes the
// queries into the workbook: the result, or what stands in the way, is the Output's. A workbook with no Power Query
// yet stops that save (the owner, 2026-11-28: "Yea optional"): Add Power Query to this workbook is the user's own
// click, and what was added is said in the Output and by the page's notice.
public partial class PowerQueryFileView
{
    // The first line of a linked file starts with this.
    private const string LinkHeader = "// workbook:";

    private WorkbookLink? _link;
    private WorkbookSave? _saved;
    private string? _linkedFor;

    /// <summary>The page reads the file again (Reload took the workbook's queries into it).</summary>
    [Parameter]
    public EventCallback OnReloaded { get; set; }

    /// <summary>The workbook this file saves into, by its name; none: a plain Power Query file.</summary>
    public string? Workbook => _link is { Linked: true } link ? link.Workbook : null;

    private static string? Header(string text)
    {
        var first = text.AsSpan().TrimStart('﻿');
        var end = first.IndexOf('\n');
        var line = (end < 0 ? first : first[..end]).Trim();
        return line.StartsWith(LinkHeader, StringComparison.OrdinalIgnoreCase) ? line.ToString() : null;
    }

    protected override async Task OnParametersSetAsync()
    {
        var wanted = Path is null || Header(Text) is not { } header ? null : $"{Path}\n{header}";
        if (wanted == _linkedFor)
        {
            return;
        }
        _linkedFor = wanted;
        await LoadLinkAsync();
    }

    private async Task LoadLinkAsync()
    {
        if (_linkedFor is null || Path is not { } path)
        {
            _link = null;
            return;
        }
        try
        {
            _link = await Ide.WorkbookLinkAsync(path, Text);
        }
        catch (ApiException error)
        {
            _link = new WorkbookLink(true, Header(Text)?[LinkHeader.Length..].Trim(), null, false, 0, false, false, error.Refusal.Error);
        }
    }

    /// <summary>The page saved the file: its queries written into its workbook. The words to say (none: the file is
    /// not linked, or the save was refused: why is in the Output).</summary>
    public Task<string?> SaveIntoWorkbookAsync() => SaveIntoWorkbookAsync(false, false);

    private static string SavedTitle(WorkbookSave saved) => (saved.Written, saved.AddsPowerQuery) switch
    {
        (true, true) => "Power Query added to the workbook",
        (true, false) => "Saved into the workbook",
        _ => "Save preview",
    };

    private async Task<string?> SaveIntoWorkbookAsync(bool force, bool add)
    {
        if (Workbook is null || Path is not { } path)
        {
            return null;
        }
        (_built, _sql, _failed) = (null, null, null);
        await MarkAsync(null, null);
        try
        {
            _saved = await Ide.SaveIntoWorkbookAsync(path, force, add);
        }
        catch (ApiException error)
        {
            _saved = null;
            _failed = SqlFailure.Of(error);
            await MarkAsync(_failed.Line, _failed.Words);
        }
        await LoadLinkAsync();
        StateHasChanged();
        return _saved?.Words;
    }

    /// <summary>Preview save: what a save would change in the workbook, each query by name. Nothing is written.</summary>
    public async Task PreviewSaveAsync()
    {
        if (Workbook is null || Path is not { } path)
        {
            return;
        }
        var text = _editor is null ? Text : await _editor.TextAsync();
        (_built, _sql, _failed) = (null, null, null);
        await MarkAsync(null, null);
        try
        {
            _saved = await Ide.PreviewWorkbookSaveAsync(path, text);
        }
        catch (ApiException error)
        {
            _saved = null;
            _failed = SqlFailure.Of(error);
            await MarkAsync(_failed.Line, _failed.Words);
        }
        StateHasChanged();
    }

    // Keep mine: this file's queries written over the workbook's, as they changed on disk.
    private Task KeepMineAsync() => SaveIntoWorkbookAsync(true, false);

    /// <summary>The page says what a save into the workbook did when the view did it by itself (Add Power Query).</summary>
    [Parameter]
    public EventCallback<string> OnSaid { get; set; }

    // Add Power Query to this workbook: the user's explicit click on a workbook that has none. The saved file's
    // queries become its first ones; what was added is the Output's first line and the page's notice.
    private async Task AddPowerQueryAsync()
    {
        if (await SaveIntoWorkbookAsync(false, true) is { } words)
        {
            await OnSaid.InvokeAsync(words);
        }
    }

    // Reload: the workbook's queries into the file; the page reads it again.
    private async Task ReloadFromWorkbookAsync()
    {
        if (Path is not { } path)
        {
            return;
        }
        try
        {
            await Ide.ReloadWorkbookAsync(path);
            (_saved, _failed) = (null, null);
            await OnReloaded.InvokeAsync();
        }
        catch (ApiException error)
        {
            _failed = SqlFailure.Of(error);
        }
        await LoadLinkAsync();
        StateHasChanged();
    }
}
