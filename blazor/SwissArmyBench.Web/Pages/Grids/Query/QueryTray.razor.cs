using System.Text.RegularExpressions;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Grids;
using SwissArmyBench.Web.Components;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Grids.Query;

public partial class QueryTray
{
    private const string AddConnection = "\u0000add";

    private IReadOnlyList<QueryConnection> _connections = [];
    private CodeEditor? _editor;
    private string _sql = string.Empty;
    private string _name = string.Empty;
    private string _from = string.Empty;
    private string _dataset = string.Empty;
    private string _status = string.Empty;
    private bool _failed;
    private bool _running;
    private bool _open = true;
    private CancellationTokenSource? _cancel;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    /// <summary>A draft (a new table, its name and Query from) or a built table's query (Run again rebuilds it).</summary>
    [Parameter]
    public bool Draft { get; set; }

    [Parameter]
    public string Sql { get; set; } = string.Empty;

    /// <summary>The draft's name, or the built table's.</summary>
    [Parameter]
    public string Name { get; set; } = string.Empty;

    /// <summary>The draft's Query from as the New query page chose it ("" the open tables).</summary>
    [Parameter]
    public string From { get; set; } = string.Empty;

    /// <summary>A built table's connection (its query runs there again).</summary>
    [Parameter]
    public string? FixedConnection { get; set; }

    /// <summary>The open tables, for the first query and the hint.</summary>
    [Parameter]
    public IReadOnlyList<string> OpenTables { get; set; } = [];

    [Parameter]
    public EventCallback<BuiltTable> OnBuilt { get; set; }

    private QueryConnection? Picked => _connections.FirstOrDefault(c => c.Name == _from);

    private string SourceTitle => Picked is { } p ? $"The query runs on {p.Name}, in its own SQL" : "The query runs in DuckDB over the open grids";

    protected override async Task OnInitializedAsync()
    {
        _name = Name;
        _from = From;
        _sql = Sql.Length > 0 || !Draft ? Sql : _from.Length > 0 ? "SELECT *\nFROM " : FirstQuery();
        _status = Draft && _from.Length == 0 ? Hint() : FixedConnection is { Length: > 0 } on ? $"Runs on {on}" : Hint(Name);
        if (Draft)
        {
            try
            {
                _connections = (await Api.GetAsync<ConnectionsListing>("/connections")).Connections.Where(c => c.RunsSql).ToList();
            }
            catch (ApiException)
            {
                _connections = [];
            }
            Report();
        }
    }

    private string FirstQuery() =>
        OpenTables.FirstOrDefault() is { } first ? $"SELECT *\nFROM {(SimpleName().IsMatch(first) ? first : $"\"{first}\"")}" : string.Empty;

    private string Hint(string? own = null)
    {
        var tables = OpenTables.Where(t => t != own).ToList();
        return tables.Count > 0 ? $"Tables: {string.Join(", ", tables)}" : "No tables open";
    }

    private void Report() =>
        _status = Picked is { } p ? $"Runs on {p.Name}, in its own SQL{(p.Dax ? " (DAX)" : string.Empty)}" : Hint();

    private void PickAsync(ChangeEventArgs e)
    {
        var picked = e.Value?.ToString() ?? string.Empty;
        if (picked == AddConnection)
        {
            Nav.NavigateTo("connections?add=1");
            return;
        }
        // A connection's own SQL starts from a plain SELECT, not the grids' table names.
        if (picked.Length > 0 && _sql.Trim() == FirstQuery().Trim())
        {
            _sql = "SELECT *\nFROM ";
        }
        else if (picked.Length == 0 && _sql.Trim() == "SELECT *\nFROM")
        {
            _sql = FirstQuery();
        }
        _from = picked;
        Report();
    }

    private async Task KeyAsync(EditorKey key)
    {
        if (key.Name == "runHere")
        {
            _sql = key.Text;
            await RunAsync();
        }
    }

    private void Cancel() => _cancel?.Cancel();

    /// <summary>The query run: a new table (the draft), or the built table again; the rows built, or the reason.</summary>
    private async Task RunAsync()
    {
        if (_editor is not null)
        {
            _sql = await _editor.TextAsync();
        }
        var sql = _sql.Trim();
        var name = Draft ? _name.Trim() : Name;
        if (Draft && !TableName().IsMatch(name))
        {
            (_status, _failed) = ("Name: 1 to 64 letters, digits, _ or -.", true);
            return;
        }
        if (sql.Length == 0)
        {
            return;
        }
        var connection = Draft ? _from : FixedConnection ?? string.Empty;
        _running = true;
        _cancel = new CancellationTokenSource();
        try
        {
            var built = connection.Length > 0
                ? await Api.PostAsync<BuiltTable>($"/datasets/{ApiClient.Part(name)}/connection-query", Body(connection, sql), _cancel.Token)
                : await Api.PostAsync<BuiltTable>($"/datasets/{ApiClient.Part(name)}/query", new { sql, replace = !Draft }, _cancel.Token);
            (_status, _failed) = ($"{Rows(built.Rows)} in {built.Dataset} (version {built.Version}).{ReadsText(built)}", false);
            OfferRefresh(built);
            await OnBuilt.InvokeAsync(built);
        }
        catch (OperationCanceledException)
        {
            (_status, _failed) = ("Cancelled.", false);
        }
        catch (ApiException error)
        {
            (_status, _failed) = (error.Message, true);
        }
        _running = false;
    }

    private object Body(string connection, string sql) => _dataset.Trim().Length > 0
        ? new { connection, sql, replace = !Draft, dataset = _dataset.Trim() }
        : new { connection, sql, replace = !Draft };

    public static string Rows(long rows) => $"{rows:N0} {(rows == 1 ? "row" : "rows")}";

    private static string ReadsText(BuiltTable built) =>
        string.Concat((built.ConnectionReads ?? []).Select(r =>
            $" {r.As}: {r.Rows:N0} rows, read {(r.ReadAt.Length > 11 ? r.ReadAt[11..] : r.ReadAt)}{(r.Sent?.Filters is { Length: > 0 } f ? $" (filters sent: {f})" : string.Empty)}."));

    /// <summary>Read from a connection's tables: Refresh reads them anew on the next Run.</summary>
    private void OfferRefresh(BuiltTable built)
    {
        var names = (built.ConnectionReads ?? []).Select(r => r.Connection).Distinct().ToList();
        if (names.Count == 0)
        {
            return;
        }
        _ = Notes.SayAsync($"Read from {string.Join(", ", names)}", "Refresh", async () =>
        {
            foreach (var connection in names)
            {
                await Api.PostAsync("/connections/sql/refresh", new { connection });
            }
            _ = Notes.SayAsync("Run again reads them anew.");
        });
    }

    [GeneratedRegex("^[A-Za-z0-9_-]{1,64}$")]
    private static partial Regex TableName();

    [GeneratedRegex("^[A-Za-z_][A-Za-z0-9_]*$")]
    private static partial Regex SimpleName();
}
