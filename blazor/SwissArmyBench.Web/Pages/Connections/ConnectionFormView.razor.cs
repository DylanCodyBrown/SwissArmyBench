using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Connections;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Connections;

public partial class ConnectionFormView
{
    private const string PythonKind = "python";
    private const string WherePart = "where";
    private const string WhoPart = "who";
    private const string SecurityPart = "security";
    private const string OptionsPart = "options";
    private const int UnrankedPlace = 9;

    /// <summary>What the file chooser offers for each file kind and each certificate file.</summary>
    private static readonly Dictionary<string, string[]> _suffixes = new()
    {
        ["csv"] = [".csv", ".tsv", ".txt"],
        ["excel"] = [".xlsx", ".xlsm", ".xls"],
        ["parquet"] = [".parquet"],
        ["json"] = [".json", ".jsonl", ".ndjson"],
        ["sqlite"] = [".db", ".sqlite", ".sqlite3"],
        ["duckdb"] = [".duckdb", ".db"],
        ["access"] = [".accdb", ".mdb"],
        ["certificate file"] = [".pem", ".crt", ".cer"],
        ["client certificate file"] = [".pem", ".crt", ".cer"],
        ["client key file"] = [".pem", ".key"],
        ["keystore"] = [".keystore", ".jks", ".jceks", ".p12", ".pfx"],
    };

    // Changes to the code one at a time (a box left for another sends two): each starts from the code the last made.
    private readonly SemaphoreSlim _turn = new(1, 1);
    private ConnectionForm? _form;
    private string _code = string.Empty;
    private string _fieldsCode = string.Empty;
    private IReadOnlyList<FormField> _fields = [];
    private List<PasswordBox> _passwords = [];
    private MissingPackages? _missing;
    private string _name = string.Empty;
    private bool _named;
    private string _description = string.Empty;
    private int? _rowLimit;
    private bool _allRows;
    private int _way;
    private string? _editing;
    private Exception? _loadError;
    private Exception? _error;
    private EventCallback _again;
    private string? _tested;
    private TablePreview? _testRows;
    private string? _rowsError;
    private string? _busyWords;
    private ElementReference _nameBox;
    private VaultSecrets? _vault;
    private bool _focused;

    [Inject]
    private ConnectionsClient Connections { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>A type's id, for a new connection.</summary>
    [Parameter]
    public string? Kind { get; set; }

    /// <summary>A saved connection's name, to change it.</summary>
    [Parameter]
    public string? Edit { get; set; }

    private bool IsVault => _form?.Connection == "vault";

    private string Heading => _editing is { } editing ? $"Edit {editing}"
        : IsVault ? $"New {ConnectionWords.Plain(_form!.Label)}"
        : $"New {ConnectionWords.Plain(_form!.Label)} connection";

    private string BackHref => _editing is { } editing ? $"connections?name={Uri.EscapeDataString(editing)}" : "connections?add=1";

    private string BackLabel => _editing ?? "Add connection";

    protected override Task OnParametersSetAsync() => LoadAsync();

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (!_focused && _form is not null && _form.Id != PythonKind)
        {
            _focused = true;
            await _nameBox.FocusAsync();
            if (IsVault && _editing is not null && _vault is not null)
            {
                await _vault.ReadAsync(); // a vault opened to edit is read at once
            }
        }
    }

    private async Task LoadAsync()
    {
        try
        {
            _editing = Edit;
            _form = Edit is not null
                ? await Connections.FormAsync(Edit)
                : (await Connections.FormsAsync()).FirstOrDefault(f => f.Id == Kind)
                  ?? throw new ApiException(0, new Refusal($"There is no connection type called {Kind}."), string.Empty);
            _code = _form.Code;
            _fieldsCode = _code;
            _fields = _form.Fields;
            _passwords = _form.Secrets.Select(s => new PasswordBox(s)).ToList();
            _missing = _form.Missing;
            // A database is named after its type until renamed; a file connection after the file chosen.
            _name = _form.Name ?? (_form.Connection == "file" ? string.Empty : ConnectionWords.Plain(_form.Label));
            _named = _form.Name is not null;
            _description = _form.Description ?? string.Empty;
            _rowLimit = _form.RowLimit is > 0 ? _form.RowLimit : null;
            _allRows = _form.RowLimit == 0;
            _way = Math.Max(0, (_form.SignIns ?? []).ToList().FindIndex(w => _code.Contains(w.Mark, StringComparison.OrdinalIgnoreCase)));
            _loadError = null;
        }
        catch (ApiException error)
        {
            _loadError = error;
        }
    }

    private void NameTyped(ChangeEventArgs e)
    {
        _name = e.Value?.ToString() ?? string.Empty;
        _named = _name.Trim().Length > 0; // emptied: not named again
    }

    /// <summary>The part of the form a setting belongs to (where, who, security, options) and its rank there.</summary>
    private string PartOf(FormField field) =>
        _form?.Options?.Contains(field.Name.ToLowerInvariant()) == true ? OptionsPart
        : _form?.FieldPlaces?.GetValueOrDefault(field.Name.ToLowerInvariant())?.Part ?? WherePart;

    private int PlaceOf(FormField field) => _form?.FieldPlaces?.GetValueOrDefault(field.Name.ToLowerInvariant())?.Rank ?? UnrankedPlace;

    /// <summary>One part's fields in the form's order (a setting the form does not rank keeps the code's order).</summary>
    private IEnumerable<FormField> Parts(string part) =>
        _fields.Select((f, i) => (f, i)).Where(x => PartOf(x.f) == part).OrderBy(x => PlaceOf(x.f)).ThenBy(x => x.i).Select(x => x.f);

    private static string ValueText(FormField field) =>
        field.Value.ValueKind == JsonValueKind.String ? field.Value.GetString() ?? string.Empty : field.Value.GetRawText();

    private static bool IsOn(FormField field) => ValueText(field).ToLowerInvariant() is "true" or "yes" or "1" or "on";

    /// <summary>On or off: True/False in the code, yes/no in a connection string (the server's rule).</summary>
    private Task FlagAsync(FormField field, ChangeEventArgs e) => FillAsync(field, e.Value is true ? "yes" : "no", false);

    private async Task BoxChangedAsync(FormField field, string text)
    {
        // A file connection is named after its file, picked or typed, until the user names it.
        if (field.Picker is not null && !_named && text.Trim().Length > 0)
        {
            _name = ConnectionWords.Stem(text.Trim());
        }
        await FillAsync(field, text, true);
    }

    private async Task BrowseAsync(FormField field)
    {
        var mode = field.Picker == "folder" ? "folder" : "file";
        var start = field.Placeholder ? null : ValueText(field);
        var suffixes = _suffixes.GetValueOrDefault(field.Name) ?? _suffixes.GetValueOrDefault(_form?.Id ?? string.Empty);
        var path = await Files.ChooseAsync(mode, field.Picker == "folder" ? "Choose folder" : "Choose file", start, "connection", suffixes);
        if (path is not null)
        {
            if (!_named)
            {
                _name = ConnectionWords.Stem(path);
            }
            await FillAsync(field, path, true);
        }
    }

    /// <summary>A changed field's value, written into the code by the server; the fields keep their boxes. A box sends
    /// its whole text (a value, or a variable's reference the code reads where it runs); a choice its value.</summary>
    private async Task FillAsync(FormField was, string value, bool boxed)
    {
        await _turn.WaitAsync();
        try
        {
            await FreshFieldsAsync();
            var field = _fields.FirstOrDefault(f => f.Name == was.Name) ?? was;
            object sent = boxed && field.Type != "flag" ? new { text = value } : value;
            var answer = await Connections.FillAsync(_code, new Dictionary<string, object?> { [field.Id] = sent }, _form?.Id, _editing);
            _code = answer.Code;
            _fieldsCode = _code;
            _fields = answer.Settings;
            await ReadVaultWhenReadyAsync();
        }
        catch (ApiException error)
        {
            Failed(error);
        }
        finally
        {
            _turn.Release();
        }
    }

    /// <summary>The fields' places in the code, read again when a password's rename moved them.</summary>
    private async Task FreshFieldsAsync()
    {
        if (_code == _fieldsCode)
        {
            return;
        }
        _fields = (await Connections.InspectAsync(_code, _form?.Id, _editing)).Settings;
        _fieldsCode = _code;
    }

    /// <summary>A vault is read on its own once it can be: every setting filled in (not a starter's placeholder).</summary>
    private async Task ReadVaultWhenReadyAsync()
    {
        if (IsVault && _vault is not null && _fields.All(f => !f.Placeholder))
        {
            await _vault.ReadAsync();
        }
    }

    /// <summary>The code edited by hand: its fields, passwords and packages read again.</summary>
    private async Task CodeEditedAsync(ChangeEventArgs e)
    {
        _code = e.Value?.ToString() ?? string.Empty;
        await InspectAgainAsync();
    }

    private async Task InspectAgainAsync()
    {
        try
        {
            var found = await Connections.InspectAsync(_code, _form?.Id, _editing);
            _fields = found.Settings;
            _fieldsCode = _code;
            _missing = found.Missing;
            if (!found.Secrets.SequenceEqual(_passwords.Select(p => p.Secret)))
            {
                _passwords = found.Secrets.Select(s => new PasswordBox(s)).ToList();
            }
            _error = null;
            await ReadVaultWhenReadyAsync();
        }
        catch (ApiException error)
        {
            Failed(error);
        }
    }

    /// <summary>Sign in: each way is its own code; switching keeps the values typed so far (with their variables).</summary>
    private async Task SwitchSignInAsync(ChangeEventArgs e)
    {
        if (_form?.SignIns is not { } ways || !int.TryParse(e.Value?.ToString(), out var at) || at < 0 || at >= ways.Count)
        {
            return;
        }
        _way = at;
        var typedSoFar = _fields
            .Where(f => !f.Placeholder || PasswordBox.NamesVariable(f.Text ?? string.Empty))
            .GroupBy(f => f.Name)
            .ToDictionary(g => g.Key, g => g.First().Type == "flag" || _form.Choices?.ContainsKey(g.Key) == true ? (object)g.First().Value : new { text = g.First().Text ?? ValueText(g.First()) });
        try
        {
            var next = await Connections.InspectAsync(ways[at].Code, _form.Id, _editing);
            var keep = next.Settings.Where(s => typedSoFar.ContainsKey(s.Name) && s.Name != "driver").ToDictionary(s => s.Id, s => (object?)typedSoFar[s.Name]);
            var answer = keep.Count > 0 ? await Connections.FillAsync(ways[at].Code, keep, _form.Id, _editing) : new FilledCode(next.Settings, ways[at].Code);
            _code = answer.Code;
            _fieldsCode = _code;
            _fields = answer.Settings;
            _passwords = next.Secrets.Select(s => new PasswordBox(s)).ToList();
            _missing = next.Missing; // the packages are this way's own
            _error = null;
            _tested = null;
            _testRows = null;
        }
        catch (ApiException error)
        {
            Failed(error);
        }
    }

    /// <summary>The form as the server takes it: its code, kind, a database's rows to open, a vault's secrets.</summary>
    private Dictionary<string, object?> Body()
    {
        var body = new Dictionary<string, object?>
        {
            ["name"] = _name.Trim(),
            ["description"] = _description.Trim(),
            ["kind"] = _form?.Kind,
            ["template"] = _form?.Id is { Length: > 0 } id ? id : null,
            ["dialect"] = _form?.Dialect,
            ["variable"] = _form?.Variable,
            ["code"] = _code,
            ["catalog"] = _form?.Catalog,
            ["secrets"] = Typed(),
        };
        if (_form?.Connection == "database")
        {
            body["row_limit"] = _allRows ? 0 : _rowLimit;
        }
        if (IsVault && _vault is not null)
        {
            body["vault_all"] = _vault.Every;
            body["vault_mapping"] = _vault.Chosen().Select(m => new { env = m.Env, secret = m.Secret }).ToList();
        }
        return body;
    }

    private async Task TestAsync()
    {
        var who = _name.Trim().Length > 0 ? _name.Trim() : ConnectionWords.Plain(_form?.Label ?? string.Empty);
        _busyWords = IsVault ? $"Reading {who}…" : $"Connecting to {who}…";
        (_tested, _testRows, _rowsError, _error) = (null, null, null, null);
        try
        {
            var answer = await Connections.TestAsync(Body());
            // Tested before it was named: the file's own name, as the server used it.
            if (answer.Name is { } named && _name.Trim().Length == 0)
            {
                _name = named;
            }
            _tested = $"It works: {ConnectionWords.Worked(answer)}.";
            _testRows = answer.Preview;
            _rowsError = answer.PreviewError;
        }
        catch (ApiException error)
        {
            Failed(error, EventCallback.Factory.Create(this, TestAsync));
        }
        _busyWords = null;
    }

    private async Task SaveAsync()
    {
        _busyWords = $"Saving {(_name.Trim().Length > 0 ? _name.Trim() : ConnectionWords.Plain(_form?.Label ?? string.Empty))}…";
        _error = null;
        try
        {
            await TypedToVariablesAsync();
            var body = Body();
            if (IsVault && _vault?.ReadNames is { } names)
            {
                body["vault_names"] = names;
            }
            if (_editing is null)
            {
                await Connections.SaveAsync(body);
            }
            else
            {
                await Connections.ChangeAsync(_editing, body);
            }
            var saved = _name.Trim();
            _ = Notes.SayAsync($"Saved {saved}.");
            Nav.NavigateTo(saved.Length > 0 ? $"connections?name={Uri.EscapeDataString(saved)}" : "connections", replace: true);
        }
        catch (ApiException error)
        {
            Failed(error);
        }
        _busyWords = null;
    }

    private void Failed(ApiException error, EventCallback again = default)
    {
        _error = error;
        _again = again;
    }
}
