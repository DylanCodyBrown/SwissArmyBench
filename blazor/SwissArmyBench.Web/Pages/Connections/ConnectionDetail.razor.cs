using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Connections;

public partial class ConnectionDetail
{
    private ConnectionUsage? _usage;
    private ConnectionTree? _tree;
    private Exception? _error;
    private string? _said;
    private string _search = string.Empty;

    [Inject]
    private ConnectionsClient Connections { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Name { get; set; } = string.Empty;

    protected override Task OnParametersSetAsync() => LoadAsync();

    private async Task LoadAsync()
    {
        try
        {
            _usage = await Connections.UsageAsync(Name);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
            return;
        }
        try
        {
            _tree = await Connections.TreeAsync(Name);
        }
        catch (ApiException)
        {
            _tree = new ConnectionTree(Name, string.Empty, []); // a kind with no tables to list here
        }
    }

    private bool Matches(TreeTable table) =>
        _search.Length == 0 || table.Table.Contains(_search, StringComparison.OrdinalIgnoreCase);

    /// <summary>A setting's value as text (a number or a switch as it is, text without its quotes).</summary>
    private static string ValueText(JsonElement value) =>
        value.ValueKind == JsonValueKind.String ? value.GetString() ?? string.Empty : value.GetRawText();

    private static string PasswordSource(PasswordPlace password) => password.From switch
    {
        "keyring" => "the system keyring",
        "vault" => password.Secret is null ? password.Vault ?? "a vault" : $"{password.Vault} ({password.Secret})",
        "environment" => "an environment variable",
        _ => "nowhere yet",
    };

    private async Task TestAsync()
    {
        await RunAsync(() => Connections.CheckAsync(Name), $"{Name} works.");
    }

    private Task RefreshAsync() => RunAsync(() => Connections.RefreshAsync(Name), "Its tables were listed again.");

    private async Task RemoveAsync()
    {
        if (await Dialogs.AskYesNoAsync($"Remove {Name}?", "The connection leaves the library; notebooks that name it stop finding it.", "Remove", danger: true))
        {
            try
            {
                await Connections.RemoveAsync(Name);
                Nav.NavigateTo("connections");
            }
            catch (ApiException error)
            {
                _error = error;
            }
        }
    }

    /// <summary>A table opened as a grid: the Grids page shows it.</summary>
    private async Task OpenTableAsync(TreeTable table)
    {
        await RunAsync(() => Connections.OpenAsync(Name, table), null);
        if (_error is null)
        {
            Nav.NavigateTo("grids");
        }
    }

    private async Task RunAsync(Func<Task> work, string? said)
    {
        _said = null;
        try
        {
            await work();
            _error = null;
            _said = said;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        await LoadAsync();
    }
}
