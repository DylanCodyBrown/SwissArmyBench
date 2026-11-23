using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Connections;

public partial class PythonConnectionForm : IDisposable
{
    // The variables are read again once typing in a box stops this long.
    private const int VariablesSettleMs = 400;

    private string _name = string.Empty;
    private string _description = string.Empty;
    private string _connect = string.Empty;
    private string _tables = string.Empty;
    private string _read = string.Empty;
    private string? _rowLimit;
    private IReadOnlyList<VariableRead> _reads = [];
    private string? _tested;
    private bool _busy;
    private string _busyWords = string.Empty;
    private Exception? _error;
    private CancellationTokenSource? _settling;

    [Inject]
    private ConnectionsClient Connections { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>The Python kind's form, or a saved Python connection's.</summary>
    [Parameter, EditorRequired]
    public ConnectionForm Form { get; set; } = default!;

    /// <summary>The saved connection's name when changing one.</summary>
    [Parameter]
    public string? Editing { get; set; }

    protected override void OnInitialized()
    {
        _name = Form.Name ?? string.Empty;
        _description = Form.Description ?? string.Empty;
        _connect = Form.Code;
        _tables = Command(Form.Catalog);
        _read = Form.Read is { } read ? Command(read) : string.Empty;
        _rowLimit = Form.RowLimit?.ToString(System.Globalization.CultureInfo.InvariantCulture);
        _reads = Form.Reads ?? [];
    }

    private static string Command(JsonElement box) =>
        box.ValueKind == JsonValueKind.Object && box.TryGetProperty("command", out var command) ? command.GetString() ?? string.Empty : string.Empty;

    private IntelContext IntelFor() => new(null, null, null, false, [], [], $"connection:{_name}", null);

    private void BoxChanged(int box, string text)
    {
        switch (box)
        {
            case 0:
                _connect = text;
                break;
            case 1:
                _tables = text;
                break;
            default:
                _read = text;
                break;
        }
        _ = ReadVariablesSoonAsync();
    }

    private async Task ReadVariablesSoonAsync()
    {
        _settling?.Cancel();
        _settling = new CancellationTokenSource();
        var mine = _settling.Token;
        try
        {
            await Task.Delay(VariablesSettleMs, mine);
            _reads = await Connections.VariablesAsync(_connect, _tables, _read);
            await InvokeAsync(StateHasChanged);
        }
        catch (OperationCanceledException)
        {
            // A newer change reads them.
        }
        catch (ApiException)
        {
            // A box that is not Python yet: the names follow when it parses.
        }
    }

    private Dictionary<string, object?> Body() => new()
    {
        ["name"] = _name.Trim().Length > 0 ? _name.Trim() : "Untitled",
        ["description"] = _description.Trim(),
        ["kind"] = "other",
        ["template"] = "python",
        ["variable"] = "conn",
        ["code"] = _connect,
        ["catalog"] = _tables.Trim().Length > 0 ? new { language = "python", command = _tables } : null,
        ["read"] = _read.Trim().Length > 0 ? new { command = _read } : null,
        ["row_limit"] = int.TryParse(_rowLimit, out var rows) ? rows : null,
    };

    private Task TestAsync() => GuardAsync($"Connecting to {(_name.Trim().Length > 0 ? _name.Trim() : "the connection")}…", async () =>
    {
        var answer = await Connections.TestAsync(Body());
        _tested = $"It works: {answer.Found ?? $"made a {answer.Type}"}.";
    });

    private Task SaveAsync() => GuardAsync($"Saving {_name.Trim()}…", async () =>
    {
        if (_name.Trim().Length == 0)
        {
            throw new ApiException(0, new Refusal("Give the connection a name."), string.Empty);
        }
        if (Editing is null)
        {
            await Connections.SaveAsync(Body());
        }
        else
        {
            await Connections.ChangeAsync(Editing, Body());
        }
        _ = Notes.SayAsync($"Saved {_name.Trim()}.");
        Nav.NavigateTo($"connections?name={Uri.EscapeDataString(_name.Trim())}");
    });

    private async Task GuardAsync(string words, Func<Task> work)
    {
        _busy = true;
        _busyWords = words;
        _tested = null;
        try
        {
            await work();
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _busy = false;
    }

    public void Dispose()
    {
        _settling?.Cancel();
        _settling?.Dispose();
        GC.SuppressFinalize(this);
    }
}
