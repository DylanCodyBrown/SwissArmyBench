using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Pages.Grids.Open;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>
/// Tables coming in (the classic openFile.ts and openMenu.ts): Open file… (the app's file chooser, a real path; a
/// workbook asks which sheets, each its own tab), a file dropped anywhere on the page (its bytes), Paste data, and
/// the Tables list. A new grid arrives as a tab by itself (the server's grid_shown notice).
/// </summary>
public partial class GridsPage
{
    private const string TablesList = "tables";
    private const string PasteData = "paste";

    private (string File, IReadOnlyList<string> Sheets, TaskCompletionSource<IReadOnlyList<string>> Answer)? _sheets;
    private DotNetObjectReference<DropTarget>? _drop;
    private IJSObjectReference? _pasteListener;
    private readonly HashSet<string> _pasting = [];

    /// <summary>The table just pasted: its name in a box (the classic "Pasted as" toast), Enter renames it.</summary>
    private string? _pasted;

    [Microsoft.AspNetCore.Components.Inject]
    private FileChooser Files { get; set; } = default!;

    /// <summary>Which sheets to open: none asked when there is one; else the list, the first ticked.</summary>
    private Task<IReadOnlyList<string>> PickSheetsAsync(string file, IReadOnlyList<string> sheets)
    {
        if (sheets.Count <= 1)
        {
            return Task.FromResult(sheets);
        }
        var answer = new TaskCompletionSource<IReadOnlyList<string>>();
        _sheets = (file, sheets, answer);
        StateHasChanged();
        return answer.Task;
    }

    private void SheetsPicked(IReadOnlyList<string> chosen)
    {
        var asked = _sheets;
        _sheets = null;
        asked?.Answer.TrySetResult(chosen);
    }

    /// <summary>Open file…: the chooser, then the file (each chosen sheet of a workbook) as a grid.</summary>
    private async Task OpenFileAsync()
    {
        try
        {
            if (await Files.ChooseAsync("file", "Open file", null, "table") is not { } path)
            {
                return;
            }
            var workbook = TableNames.IsWorkbook(path);
            var sheets = workbook ? (await Api.PostAsync<SheetsAnswer>("/files/sheets", new { path })).Sheets : [];
            IReadOnlyList<string?> chosen = workbook ? [.. await PickSheetsAsync(path, sheets)] : [null];
            foreach (var sheet in chosen)
            {
                var name = TableNames.FromFile(path, sheets.Count > 1 ? sheet : null);
                await Api.PostAsync($"/datasets/{ApiClient.Part(name)}/load", sheet is null ? new { path } : new { path, sheet });
            }
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>Files dropped on the page are told to this page (once, as it opens).</summary>
    private async Task ListenForDropsAsync()
    {
        _drop = DotNetObjectReference.Create(new DropTarget(this));
        await Js.InvokeVoidAsync("sab.fileDrop", _drop);
        _pasteListener = await Js.InvokeAsync<IJSObjectReference>("sab.pagePaste", _drop);
    }

    /// <summary>Ctrl+V of a table: a new table named for the local time (never an open table's name), then its name
    /// in the Pasted as box.</summary>
    internal async Task PastedTableAsync(string text)
    {
        var stamp = DateTime.Now.ToString("HHmmss", System.Globalization.CultureInfo.InvariantCulture);
        try
        {
            var taken = (await Api.GetAsync<DatasetsAnswer>("/datasets")).Datasets.Select(d => d.Name).ToHashSet();
            var name = Enumerable.Range(2, 1000).Select(n => $"pasted_{stamp}_{n}").Prepend($"pasted_{stamp}").First(n => !taken.Contains(n) && !_pasting.Contains(n));
            _pasting.Add(name); // a second paste before this one lands picks another name
            await Js.InvokeVoidAsync("sab.postText", $"/datasets/{name}/paste", text);
            _pasted = name;
            StateHasChanged();
        }
        catch (JSException error)
        {
            _ = Notes.SayAsync(error.Message);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>A file dropped on the page: its bytes, each chosen sheet of a workbook its own grid.</summary>
    internal async Task DroppedAsync(int id, string file)
    {
        try
        {
            var workbook = TableNames.IsWorkbook(file);
            IReadOnlyList<string> sheets = workbook ? await Js.InvokeAsync<List<string>>("sab.droppedSheets", id) : [];
            IReadOnlyList<string?> chosen = workbook ? [.. await PickSheetsAsync(file, sheets)] : [null];
            foreach (var sheet in chosen)
            {
                await Js.InvokeVoidAsync("sab.dropAs", id, TableNames.FromFile(file, sheets.Count > 1 ? sheet : null), sheet);
            }
        }
        catch (JSException error)
        {
            _ = Notes.SayAsync($"{file}: {error.Message}");
        }
        await Js.InvokeVoidAsync("sab.forgetDropped", id);
    }
}
