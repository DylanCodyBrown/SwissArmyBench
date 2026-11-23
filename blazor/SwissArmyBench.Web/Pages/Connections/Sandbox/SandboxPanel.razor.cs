using System.Globalization;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Sandbox;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Connections.Sandbox;

public sealed partial class SandboxPanel : IDisposable
{
    private const string SortKey = "sandbox.sort";
    private const int SettleMilliseconds = 150;

    /// <summary>The sortable headings: a click sorts by it; again, the other way.</summary>
    private static readonly (string Key, string Words)[] _sortHeads =
        [("name", "Table"), ("rows", "Rows"), ("source", "From"), ("created", "Created"), ("changed", "Last changed")];

    private SandboxState? _state;
    private string _sort = "name";
    private string _order = "asc";
    private string? _busyWords;
    private Exception? _error;
    private bool _adding;
    private CancellationTokenSource? _settle;

    [Inject]
    private SandboxClient Sandbox { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        var kept = await Js.InvokeAsync<string?>("sab.recall", SortKey) ?? "name asc";
        var parts = kept.Split(' ');
        _sort = parts[0].Length > 0 ? parts[0] : "name";
        _order = parts.Length > 1 && parts[1] == "desc" ? "desc" : "asc";
        await DrawAsync();
    }

    private async Task DrawAsync()
    {
        try
        {
            _state = await Sandbox.StateAsync(_sort, _order);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
            _state ??= new SandboxState(null, [], []);
        }
    }

    private async Task SortAsync(string key)
    {
        _order = key == _sort && _order == "asc" ? "desc" : "asc";
        _sort = key;
        await Js.InvokeVoidAsync("sab.remember", SortKey, $"{_sort} {_order}");
        await DrawAsync();
    }

    /// <summary>"Mock of Warehouse (sqlserver)" or the plain DuckDB client: the client a table's rows answer as.</summary>
    private static string ClientWords(SandboxMock client)
    {
        if (client.Connection is null || client.Kind == "duckdb")
        {
            return "Plain DuckDB client";
        }
        var what = client.Template ?? client.Kind switch
        {
            "dataverse" => "Dataverse",
            "sharepoint" => "SharePoint",
            "powerbi" => "Power BI",
            "python" => "Python",
            var kind => kind,
        };
        return $"Mock of {client.Connection} ({what})";
    }

    private static string ChangeWords(SandboxChanges changes) => string.Join(", ", new[]
    {
        changes.Inserted > 0 ? $"{changes.Inserted} inserted" : string.Empty,
        changes.Updated > 0 ? $"{changes.Updated} updated" : string.Empty,
        changes.Deleted > 0 ? $"{changes.Deleted} deleted" : string.Empty,
    }.Where(w => w.Length > 0));

    private static string When(string? at) =>
        at is not null && DateTimeOffset.TryParse(at, CultureInfo.InvariantCulture, DateTimeStyles.None, out var when)
            ? when.ToLocalTime().ToString("g", CultureInfo.CurrentCulture)
            : string.Empty;

    private async Task ActAsync(string words, Func<Task> work, string said)
    {
        _busyWords = words;
        try
        {
            await work();
            if (said.Length > 0)
            {
                _ = Notes.SayAsync(said);
            }
            await DrawAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _busyWords = null;
    }

    private async Task MockAsync(SandboxTable table, string? connection) =>
        await ActAsync("Saving…", () => Sandbox.MockAsync(table.Name, connection is { Length: > 0 } ? connection : null), string.Empty);

    private async Task SaveCheckpointAsync()
    {
        var name = await Dialogs.AskTextAsync("Save checkpoint", string.Empty, "Checkpoint name", $"Checkpoint {DateTime.Now:HH.mm.ss}", "Save");
        if (name is { Length: > 0 })
        {
            await ActAsync("Saving…", () => Sandbox.SaveCheckpointAsync(name.Trim()), string.Empty);
        }
    }

    private async Task AddedAsync(bool added)
    {
        _adding = false;
        if (added)
        {
            await DrawAsync();
        }
    }

    private void OnNotice(Notice notice)
    {
        if (notice.Type is not ("sandbox_changed" or "project_changed"))
        {
            return;
        }
        _settle?.Cancel();
        _settle = new CancellationTokenSource();
        var token = _settle.Token;
        _ = InvokeAsync(async () =>
        {
            try
            {
                await Task.Delay(SettleMilliseconds, token);
            }
            catch (TaskCanceledException)
            {
                return;
            }
            await DrawAsync();
            StateHasChanged();
        });
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        _settle?.Cancel();
        _settle?.Dispose();
    }
}
