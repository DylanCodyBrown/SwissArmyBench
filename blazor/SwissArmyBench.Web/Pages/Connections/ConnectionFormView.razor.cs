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
    private const string WhoPart = "who";
    private const string OtherPart = "other";

    /// <summary>The form's parts, in the classic form's order and words.</summary>
    private static readonly (string Part, string Title)[] _parts =
    [
        ("where", "Where it is"),
        (WhoPart, "Who signs in"),
        ("security", "Security"),
        (OtherPart, "Settings"),
    ];

    private ConnectionForm? _form;
    private string _code = string.Empty;
    private IReadOnlyList<FormField> _fields = [];
    private string _name = string.Empty;
    private string _description = string.Empty;
    private Dictionary<string, string> _secrets = [];
    private string? _editing;
    private Exception? _error;
    private string? _tested;
    private bool _busy;

    [Inject]
    private ConnectionsClient Connections { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>A kind's id, for a new connection.</summary>
    [Parameter]
    public string? Kind { get; set; }

    /// <summary>A saved connection's name, to change it.</summary>
    [Parameter]
    public string? Edit { get; set; }

    protected override Task OnParametersSetAsync() => LoadAsync();

    private async Task LoadAsync()
    {
        try
        {
            _editing = Edit;
            _form = Edit is not null
                ? await Connections.FormAsync(Edit)
                : (await Connections.FormsAsync()).FirstOrDefault(f => f.Id == Kind);
            if (_form is null)
            {
                _error = new ApiException(0, new Refusal($"There is no kind of connection called {Kind}."), string.Empty);
                return;
            }
            _code = _form.Code;
            _fields = _form.Fields;
            _name = _form.Name ?? string.Empty;
            _description = _form.Description ?? string.Empty;
            _secrets = _form.Secrets.ToDictionary(s => s, _ => string.Empty);
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>The fields of one part, in the order the backend gives; a field no part names goes in Settings.</summary>
    private IEnumerable<FormField> FieldsOf(string part)
    {
        var order = _form?.FieldOrder ?? new Dictionary<string, IReadOnlyList<string>>();
        if (part == OtherPart)
        {
            var placed = order.Values.SelectMany(names => names).ToHashSet();
            return _fields.Where(f => !placed.Contains(f.Name));
        }
        return order.TryGetValue(part, out var names) ? names.Select(n => _fields.FirstOrDefault(f => f.Name == n)).OfType<FormField>() : [];
    }

    /// <summary>A setting's name in words: "tenant_id" as "Tenant id".</summary>
    private static string Label(string name)
    {
        var words = name.Replace('_', ' ');
        return words.Length == 0 ? words : char.ToUpperInvariant(words[0]) + words[1..];
    }

    private static string TextOf(FormField field) =>
        field.Value.ValueKind == JsonValueKind.String ? field.Value.GetString() ?? string.Empty : field.Value.GetRawText();

    /// <summary>A value written into the code where the field stands (the server's rule), then the fields again.</summary>
    private async Task FillAsync(FormField field, string value)
    {
        object sent = field.Type == "number" && double.TryParse(value, out var number) ? number : value;
        try
        {
            var filled = await Connections.FillAsync(_code, field.Id, sent, _form?.Id, _editing);
            _code = filled.Code;
            _fields = filled.Settings;
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task PickAsync(FormField field)
    {
        var mode = field.Picker == "folder" ? "folder" : "open";
        var path = await Files.ChooseAsync(mode, Label(field.Name), null, "connection");
        if (path is not null)
        {
            await FillAsync(field, path);
        }
    }

    /// <summary>The form as the server takes it (the classic page's sent()): its code, kind and the passwords typed.</summary>
    private Dictionary<string, object?> Body() => new()
    {
        ["name"] = _name.Trim(),
        ["description"] = _description.Trim(),
        ["kind"] = _form?.Kind,
        ["template"] = _form?.Id,
        ["dialect"] = _form?.Dialect,
        ["variable"] = _form?.Variable,
        ["code"] = _code,
        ["catalog"] = _form?.Catalog,
        ["secrets"] = _secrets.Where(s => s.Value.Length > 0).ToDictionary(s => s.Key, s => s.Value),
    };

    private async Task TestAsync()
    {
        _busy = true;
        _tested = null;
        try
        {
            var answer = await Connections.TestAsync(Body());
            _tested = $"It works{(answer.Found is null ? string.Empty : $": {answer.Found}")}.";
            if (_name.Length == 0 && answer.Name is not null)
            {
                _name = answer.Name;
            }
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _busy = false;
    }

    private async Task SaveAsync()
    {
        if (_name.Trim().Length == 0)
        {
            _error = new ApiException(0, new Refusal("Give the connection a name."), string.Empty);
            return;
        }
        _busy = true;
        try
        {
            var body = Body();
            if (_editing is null)
            {
                await Connections.SaveAsync(body);
            }
            else
            {
                await Connections.ChangeAsync(_editing, body);
            }
            _ = Notes.SayAsync($"Saved {_name.Trim()}.");
            Nav.NavigateTo($"connections?name={Uri.EscapeDataString(_name.Trim())}");
        }
        catch (ApiException error)
        {
            _error = error;
        }
        _busy = false;
    }
}
