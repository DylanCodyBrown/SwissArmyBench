using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids.Open;

public partial class TablesDialog
{
    private static readonly HashSet<string> _redrawOn = ["processes_changed", "grid_shown", "grid_closed", "dataset_closed", "dataset_updated", "dataset_renamed"];

    private IReadOnlyList<DatasetEntry>? _datasets;
    private IReadOnlyList<SessionTables> _sessions = [];
    private string _budget = string.Empty;
    private string? _sessionsWords;
    private Exception? _error;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private LiveUpdates Live { get; set; } = default!;

    [Parameter]
    public EventCallback OnClose { get; set; }

    protected override async Task OnInitializedAsync()
    {
        Live.NoticeArrived += OnNotice;
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        try
        {
            var listing = await Api.GetAsync<DatasetsAnswer>("/datasets");
            var b = listing.Budget;
            _budget = $"{b.Used} of {b.Total} in use · {b.Datasets} of {b.MaxDatasets} tables · {b.Grids} of {b.MaxGrids} tabs";
            _datasets = listing.Datasets;
        }
        catch (ApiException error)
        {
            _budget = $"Could not read the tables: {error.Message}";
        }
        try
        {
            _sessions = (await Api.GetAsync<ProcessesAnswer>("/processes")).Processes;
            _sessionsWords = _sessions.Count > 0 ? null : "No Python sessions";
        }
        catch (ApiException error)
        {
            _sessionsWords = $"Could not read the Python sessions: {error.Message}";
        }
    }

    /// <summary>A grid on the table itself: the original comes back as a tab, in front, and this list closes.</summary>
    private async Task OpenClosedAsync(DatasetEntry d)
    {
        try
        {
            await Api.PostAsync("/grids", new { dataset = d.Name });
            await OnClose.InvokeAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task RemoveAsync(DatasetEntry d)
    {
        var closed = d.Grids.Count == 0;
        var asked = $"Remove {d.Name} from memory? {(closed ? "Nothing" : "Its tabs close too; nothing")} is saved.";
        if (!await Dialogs.AskYesNoAsync(asked, string.Empty, "OK", danger: true))
        {
            return;
        }
        try
        {
            await Api.DeleteAsync($"/datasets/{ApiClient.Part(d.Name)}");
            await LoadAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task AskToOpenAsync(SessionTables session, SessionTable table)
    {
        try
        {
            await Api.PostAsync($"/processes/{ApiClient.Part(session.Id)}/open", new { name = table.Name });
        }
        catch (ApiException error)
        {
            _error = new ApiException(error.Status, error.Refusal with { Error = $"Could not ask {session.Label} for {table.Name}: {error.Message}" }, error.Body);
        }
    }

    private async Task OpenAllAsync(SessionTables session, IReadOnlyList<SessionTable> closed)
    {
        foreach (var table in closed)
        {
            await AskToOpenAsync(session, table);
        }
    }

    private static string KindLabel(string kind) => kind switch
    {
        "dataframe" => "DataFrame",
        "polars" => "Polars",
        "arrow" => "Arrow",
        "relation" => "DuckDB relation",
        "table" => "DuckDB table",
        _ => kind,
    };

    private static string SizeOf(SessionTable table) =>
        $"{(table.Rows is { } rows ? rows.ToString("N0") : "?")} × {(table.Columns is { } columns ? columns.ToString("N0") : "?")}";

    private void OnNotice(Notice notice)
    {
        if (_redrawOn.Contains(notice.Type))
        {
            _ = InvokeAsync(async () =>
            {
                await LoadAsync();
                StateHasChanged();
            });
        }
    }

    public void Dispose()
    {
        Live.NoticeArrived -= OnNotice;
        GC.SuppressFinalize(this);
    }
}
