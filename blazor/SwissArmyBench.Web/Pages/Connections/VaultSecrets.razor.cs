using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;

namespace SwissArmyBench.Web.Pages.Connections;

public partial class VaultSecrets
{
    private readonly List<VaultRow> _rows = [];
    private Dictionary<string, string>? _taken;
    private string _filter = string.Empty;
    private string _newSecret = string.Empty;
    private bool _reading;
    private bool _listed;
    private string? _said;
    private Exception? _error;
    private ElementReference _newBox;
    private int _readings;

    [Inject]
    private ConnectionsClient Connections { get; set; } = default!;

    /// <summary>The form's body as Read the vault sends it (its code and settings, the passwords typed).</summary>
    [Parameter, EditorRequired]
    public Func<Dictionary<string, object?>> Body { get; set; } = default!;

    /// <summary>The vault edited (its own variables are not "taken"), or null for a new one.</summary>
    [Parameter]
    public string? Editing { get; set; }

    /// <summary>Every secret at first (a new vault's default; a saved one's own choice).</summary>
    [Parameter]
    public bool EveryAtFirst { get; set; } = true;

    /// <summary>Every secret, each under its own name (new ones too).</summary>
    public bool Every { get; private set; }

    /// <summary>A saved vault's secrets and their variables.</summary>
    [Parameter]
    public IReadOnlyList<VaultMapping> Mapping { get; set; } = [];

    /// <summary>The names the last read listed: kept with the save, so the vault's variables are there at once.</summary>
    public IReadOnlyList<string>? ReadNames { get; private set; }

    protected override async Task OnInitializedAsync()
    {
        Every = EveryAtFirst;
        foreach (var m in Editing is null ? [] : Mapping)
        {
            Add(m.Secret, m.Env, true);
        }
        try
        {
            _taken = (await Connections.TakenAsync())
                .Where(v => v.From == "vault" ? v.Vault != Editing : v.Kept is { Length: > 0 })
                .GroupBy(v => v.Name)
                .ToDictionary(g => g.Key, g => g.First().From == "vault" ? g.First().Vault ?? "a key vault" : "your variables");
        }
        catch (ApiException)
        {
            _taken = null; // no inline check
        }
    }

    /// <summary>What Save keeps: every secret keeps only the ones given another name; otherwise the ones ticked.</summary>
    public IReadOnlyList<VaultMapping> Chosen() => _rows
        .Where(r => Every ? r.Variable.Trim().Length > 0 && r.Variable.Trim() != VaultRow.EnvFor(r.Secret) : r.Use)
        .Select(r => new VaultMapping(r.Variable.Trim().Length > 0 ? r.Variable.Trim() : VaultRow.EnvFor(r.Secret), r.Secret))
        .ToList();

    /// <summary>Read the vault's names (never a value); a newer read answers instead of an older one.</summary>
    public async Task ReadAsync()
    {
        var mine = ++_readings;
        _reading = true;
        _error = null;
        _said = null;
        StateHasChanged();
        try
        {
            var answer = await Connections.VaultSecretsAsync(Body());
            if (mine != _readings)
            {
                return;
            }
            if (answer.Names is null)
            {
                _listed = false;
                _said = "This vault does not list its secrets: add them by name.";
                await _newBox.FocusAsync();
            }
            else
            {
                ReadNames = answer.Names.Select(m => m.Secret).ToList();
                foreach (var m in answer.Names)
                {
                    Add(m.Secret, string.Empty, false);
                }
                _listed = true;
                _said = ConnectionWords.Count(answer.Names.Count, "secret");
            }
        }
        catch (ApiException error)
        {
            if (mine == _readings)
            {
                _error = error;
            }
        }
        _reading = false;
        StateHasChanged();
    }

    private void Add(string secret, string variable, bool use)
    {
        if (_rows.Any(r => r.Secret == secret))
        {
            return;
        }
        var own = VaultRow.EnvFor(secret);
        _rows.Add(new VaultRow(secret, variable.Length > 0 && variable != own ? variable : string.Empty, use));
    }

    private bool Shown(VaultRow row) =>
        _filter.Length == 0 || $"{row.Secret} {row.Variable} {VaultRow.EnvFor(row.Secret)}".Contains(_filter, StringComparison.OrdinalIgnoreCase);

    private string? TakenBy(VaultRow row) => row.Variable.Trim() is { Length: > 0 } typed ? _taken?.GetValueOrDefault(typed) : null;

    private static void Typed(VaultRow row, string text)
    {
        row.Variable = text;
        row.Use = true;
    }

    private async Task AddTypedAsync()
    {
        var secret = _newSecret.Trim();
        if (secret.Length == 0)
        {
            return;
        }
        Add(secret, string.Empty, true);
        _newSecret = string.Empty;
        await _newBox.FocusAsync();
    }

    private async Task NewKeyAsync(KeyboardEventArgs e)
    {
        if (e.Key == "Enter")
        {
            await AddTypedAsync();
        }
    }
}
