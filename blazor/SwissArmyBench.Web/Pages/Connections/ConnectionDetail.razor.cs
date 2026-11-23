using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Connections;

public partial class ConnectionDetail
{
    private ConnectionUsage? _usage;
    private ListedConnection? _listed;
    private Exception? _error;
    private Exception? _testError;
    private TablePreview? _testRows;
    private string? _busyWords;
    private IReadOnlyList<string>? _sheets;

    [Inject]
    private ConnectionsClient Connections { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Parameter, EditorRequired]
    public string Name { get; set; } = string.Empty;

    /// <summary>Its status for the page's heading (the word and why).</summary>
    [Parameter]
    public EventCallback<(string Status, string? Why)> OnStatus { get; set; }

    /// <summary>A starter's connection: read-only (no Edit, no Remove).</summary>
    private bool ReadOnly => _listed?.Source == "starter";

    protected override async Task OnParametersSetAsync()
    {
        _usage = null;
        _testRows = null;
        _testError = null;
        await LoadAsync();
    }

    private async Task LoadAsync()
    {
        try
        {
            var usage = Connections.UsageAsync(Name);
            var listed = Connections.ListedAsync();
            _usage = await usage;
            _listed = (await listed).FirstOrDefault(c => c.Name == Name);
            _error = null;
            var why = _usage.Status == "needs" ? string.Join(", ", _usage.Missing ?? []) : _usage.Error;
            await OnStatus.InvokeAsync((_usage.Status, why.Length > 0 ? why : null));
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The configuration's terms, in the classic order (never a password's value); `Missing` marks a
    /// password with no source on this computer.</summary>
    private IEnumerable<(string Term, string Value, bool Missing)> Terms(ConnectionUsage usage)
    {
        var config = usage.Configuration;
        yield return ("Type", _listed?.Type is { Length: > 0 } type ? ConnectionWords.Plain(type) : config.Type.Length > 0 ? config.Type : config.Dialect, false);
        if (config.Description.Length > 0)
        {
            yield return ("Description", config.Description, false);
        }
        if (config.SignIn is { Length: > 0 } signIn)
        {
            yield return ("Sign in", signIn, false);
        }
        if (usage.About is { Count: > 0 } about)
        {
            yield return ("Server", string.Join("\n", about), false);
        }
        foreach (var setting in config.Settings)
        {
            yield return (ConnectionWords.Words(setting.Name), SettingText(setting.Value), false);
        }
        foreach (var password in config.Passwords)
        {
            yield return (ConnectionWords.Words(password.Name), ConnectionWords.PasswordSource(password), password.From == "missing");
        }
        foreach (var variable in config.Variables ?? [])
        {
            yield return (variable.Name, variable.From == "vault" ? $"{variable.Vault} ({variable.Secret})" : variable.From, false);
        }
        if (config.VaultAll)
        {
            yield return ("Secrets", "Every secret, each under its own name", false);
        }
        foreach (var entry in config.VaultEntries ?? [])
        {
            yield return (entry.Variable, entry.Secret, false);
        }
        if (config.RowLimit is { } rows)
        {
            yield return ("Rows to open", rows == 0 ? "Every row" : rows.ToString("N0"), false);
        }
        if (_listed is { } listed)
        {
            yield return ("In code", ConnectionWords.InCode(Name, listed.Connection, listed.Dialect), false);
        }
        if (usage.Writes is { } writes)
        {
            yield return writes.Writable ? ("Writes", WritesWords(writes), false) : ("Read-only", writes.Reason, false);
        }
    }

    private static string WritesWords(WritesInfo writes)
    {
        var said = writes.Starters is { Count: > 0 } starters ? $"{string.Join(", ", writes.Operations ?? [])} ({string.Join(", ", starters)})" : writes.How;
        return writes.Note.Length > 0 ? $"{said} ({writes.Note})" : said;
    }

    /// <summary>A setting's value as text: a switch as Yes or No, a number as it is, text without its quotes.</summary>
    private static string SettingText(JsonElement value) => value.ValueKind switch
    {
        JsonValueKind.True => "Yes",
        JsonValueKind.False => "No",
        JsonValueKind.String => value.GetString() ?? string.Empty,
        _ => value.GetRawText(),
    };

    private static string RefIcon(ConnectionReference reference) => reference.Kind switch
    {
        "grid" => "grids",
        "script" => "code",
        "app" => "page",
        _ => "notebook",
    };

    private static string RefWhere(ConnectionReference reference) => reference.Kind switch
    {
        "grid" => "an open grid",
        "app" => $"{reference.Page ?? "a page"} · {reference.Line}",
        _ when reference.Cell is { } cell => $"@cell{cell}{(reference.Name is { } named ? $" {named}" : string.Empty)}",
        _ => "main code",
    };

    /// <summary>A reference's click: its grid on the Grids page, or its document on its kind's page at its cell.</summary>
    private void OpenReference(ConnectionReference reference)
    {
        if (reference.Kind == "grid" && reference.Grid is { } grid)
        {
            Nav.NavigateTo($"grids?grid={Uri.EscapeDataString(grid)}");
            return;
        }
        var page = reference.Kind == "script" ? "scripts" : "notebooks";
        var cell = reference.Cell is { } at ? $"&cell={at}" : string.Empty;
        Nav.NavigateTo($"{page}?path={Uri.EscapeDataString(reference.Document)}{cell}");
    }

    private Task TestAsync() => GuardAsync("Testing…", async () =>
    {
        _testRows = null;
        _testError = null;
        try
        {
            var answer = await Connections.CheckAsync(Name);
            _ = Notes.SayAsync($"{Name} works: {ConnectionWords.Worked(answer)}.");
            if (_listed is { } c && (c.Connection == "python" || ConnectionWords.ReadsByCode(c.Dialect)))
            {
                _testRows = answer.Preview;
            }
        }
        catch (ApiException error)
        {
            _testError = error;
        }
        await LoadAsync();
    });

    private Task RefreshAsync() => GuardAsync("Refreshing…", async () =>
    {
        _testError = null;
        try
        {
            var answer = await Connections.RefreshAsync(Name);
            _ = Notes.SayAsync($"{Name}: {answer.Catalog.Tables} tables, {answer.Catalog.Columns} columns");
        }
        catch (ApiException error)
        {
            _testError = error;
        }
        await LoadAsync();
    });

    private Task ImportRelationshipsAsync() => GuardAsync("Reading…", async () =>
    {
        _ = Notes.SayAsync($"Reading {Name}'s relationships…");
        var answer = await Connections.RelationshipsAsync(Name);
        var n = answer.Imported.Count;
        var changed = answer.Changed is { Count: > 0 } c ? $" Changed: {string.Join("; ", c)}." : string.Empty;
        _ = Notes.SayAsync($"{ConnectionWords.Count(n, "relationship")} from {Name} {(n == 1 ? "is" : "are")} in the model.{changed}");
    });

    private Task SqlEndpointAsync() => GuardAsync("Switching…", async () =>
    {
        await Connections.SqlEndpointAsync(Name);
        await LoadAsync();
    });

    private Task UpdateDriverAsync() => GuardAsync("Updating…", async () =>
    {
        try
        {
            await Connections.UpdateDriverAsync(Name);
            _ = Notes.SayAsync($"{Name} now uses mssql-python: no ODBC driver.");
            await LoadAsync();
        }
        catch (ApiException error)
        {
            _testError = error;
        }
    });

    private async Task CopyForPythonAsync()
    {
        await Js.InvokeAsync<bool>("sab.copy", $"conn = sab.connection(\"{Name}\")");
        _ = Notes.SayAsync("Copied");
    }

    private async Task RemoveAsync()
    {
        var vault = _usage?.Configuration.Kind == "vault";
        var words = vault ? $"Remove the key vault {Name}? Its variables stop being set." : $"Remove the connection {Name}? Its saved passwords go too.";
        if (!await Dialogs.AskYesNoAsync($"Remove {Name}", words, "Remove", danger: true))
        {
            return;
        }
        await GuardAsync("Removing…", async () =>
        {
            var gone = await Connections.RemoveAsync(Name);
            if (gone.RelationshipsRemoved is var n and > 0)
            {
                _ = Notes.SayAsync($"Removed {ConnectionWords.Count(n, "relationship")} that came from {Name}.");
            }
            Nav.NavigateTo("connections", replace: true);
        });
    }

    /// <summary>A file connection's file as a grid: a workbook asks which sheets first.</summary>
    private Task OpenFileAsync() => GuardAsync("Opening…", async () =>
    {
        var answer = await Connections.OpenFileAsync(Name);
        if (answer.Sheets is { } sheets)
        {
            _sheets = sheets;
            return;
        }
        _ = Notes.SayAsync($"{answer.Dataset} is open as a grid.");
        Nav.NavigateTo("grids");
    });

    private Task SheetsChosenAsync(IReadOnlyList<string> chosen) => GuardAsync("Opening…", async () =>
    {
        _sheets = null;
        foreach (var sheet in chosen)
        {
            await Connections.OpenFileAsync(Name, sheet);
        }
        if (chosen.Count > 0)
        {
            Nav.NavigateTo("grids");
        }
    });

    private async Task GuardAsync(string words, Func<Task> work)
    {
        _busyWords = words;
        try
        {
            await work();
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _busyWords = null;
    }
}
