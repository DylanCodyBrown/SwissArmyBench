using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api.PowerApps;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.CodeApp;

public partial class CodeAppConnectorsTab : IDisposable
{
    // The search asks again this long after typing stops.
    private const int SearchMs = 250;

    private IReadOnlyList<CodeAppConnector>? _connectors;
    private CodeAppExplored? _explored;
    private CodeAppConnector? _connector;
    private CodeAppOperation? _operation;
    private string _query = string.Empty;
    private bool _refreshing;
    private CancellationTokenSource? _wait;
    private (CodeAppConnector Connector, IReadOnlyList<CodeAppConnection> Connections)? _adding;

    [Inject]
    private CodeAppClient CodeApps { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Parameter, EditorRequired]
    public CodeAppProject Project { get; set; } = new();

    [Parameter, EditorRequired]
    public CodeAppPage Host { get; set; } = default!;

    protected override Task OnInitializedAsync() => FillAsync(refresh: false);

    /// <summary>The service the app calls a connector through ("shared_office365" is Office365Service).</summary>
    private static string ServiceName(string name)
    {
        var bare = name.StartsWith("shared_", StringComparison.Ordinal) ? name[7..] : name;
        return bare.Length == 0 ? "Service" : $"{char.ToUpperInvariant(bare[0])}{bare[1..]}Service";
    }

    private async Task FillAsync(bool refresh)
    {
        if (await Host.CallAsync(() => CodeApps.ConnectorsAsync(_query.Trim(), refresh)) is { } got)
        {
            _connectors = got.Connectors;
        }
        else
        {
            _connectors ??= [];
        }
    }

    private async Task RefreshAsync()
    {
        _refreshing = true;
        await FillAsync(refresh: true);
        _refreshing = false;
    }

    private async Task SearchSoonAsync()
    {
        _wait?.Cancel();
        var wait = _wait = new CancellationTokenSource();
        try
        {
            await Task.Delay(SearchMs, wait.Token);
        }
        catch (TaskCanceledException)
        {
            return;
        }
        await FillAsync(refresh: false);
    }

    private async Task ExploreAsync(CodeAppConnector c)
    {
        if (await Host.CallAsync(() => CodeApps.ConnectorAsync(c.Name)) is { } got)
        {
            (_explored, _connector, _operation) = (got, c, got.Operations.FirstOrDefault());
        }
    }

    private async Task AddAsync(CodeAppConnector c)
    {
        if (!Project.Open)
        {
            Notes.Error(new InvalidOperationException("Open a code app first (Project)."));
            return;
        }
        if (await Host.CallAsync(() => CodeApps.ConnectionsAsync(c.Name)) is { } got)
        {
            _adding = (c, got.Connections);
        }
    }

    private async Task AddedAsync(string name)
    {
        _adding = null;
        await Notes.SayAsync($"Added {name}.");
        await Host.LoadAsync();
    }

    public void Dispose()
    {
        _wait?.Cancel();
        _wait?.Dispose();
    }
}
