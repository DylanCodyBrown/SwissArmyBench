using System.Text.Json;
using System.Text.RegularExpressions;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Apis;
using SwissArmyBench.Web.Api.Files;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Apis;

/// <summary>Add API (the classic addApi.ts): an OpenAPI document (its address, a file, pasted) or the endpoints listed
/// by hand; the name, where it is hosted (a preset fills the address and the sign-in), the base address and Find its
/// OpenAPI; the sign-in and its settings, a box per variable for Try it; the preview as the form changes (written
/// nowhere), Try it, and Add.</summary>
public sealed partial class AddApiForm : IDisposable
{
    private const int PreviewPauseMilliseconds = 450;

    private AddApiChoices? _choices;
    private Exception? _error;
    private string? _said;
    private string? _mode;
    private string _url = string.Empty;
    private string _pasted = string.Empty;
    private string _file = string.Empty;
    private string _name = string.Empty;
    private bool _named;
    private string _preset = string.Empty;
    private string _baseUrl = string.Empty;
    private string _authValue = "type:none";
    private Dictionary<string, string> _auth = new() { ["type"] = "none" };
    private bool _authTouched;
    private Dictionary<string, string>? _documentAuth;
    private readonly List<EndpointCard> _cards = [new()];
    private readonly Dictionary<string, string> _values = [];
    private AddApiPlan? _plan;
    private bool _previewing;
    private int _asked;
    private CancellationTokenSource? _waiting;
    private string? _trying;
    private (string Key, TriedOperation? Rows, Exception? Error)? _tried;
    private bool _adding;

    [Inject]
    private ApisClient Apis { get; set; } = default!;

    [Inject]
    private FileChooser Files { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>Added: the API's name (its explorer follows).</summary>
    [Parameter]
    public EventCallback<string> OnAdded { get; set; }

    protected override async Task OnInitializedAsync()
    {
        try
        {
            _choices = await Apis.ChoicesAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private ApiPreset? Preset => _choices?.Presets.FirstOrDefault(p => p.Id == _preset);

    private AuthKind? AuthType => _choices?.AuthTypes.FirstOrDefault(t => t.Id == _auth.GetValueOrDefault("type"));

    private bool CanFind => Preset is { SpecPaths.Count: > 0 } && Root(_baseUrl) is not null;

    private static string? Root(string url) => SiteRoot().Match(url.Trim()) is { Success: true } m ? m.Groups[1].Value : null;

    private static Dictionary<string, string> AuthOf(IReadOnlyDictionary<string, JsonElement> found) =>
        found.Where(p => p.Key != "label").ToDictionary(p => p.Key, p => p.Value.ValueKind == JsonValueKind.String ? p.Value.GetString() ?? string.Empty : p.Value.ToString());

    private void Pick(string mode)
    {
        _mode = mode;
        ChooseDefaultAuth();
        Later();
    }

    /// <summary>The sign-in box's value as the form changes: the document's own scheme until the user picks one.</summary>
    private void ChooseDefaultAuth()
    {
        if (!_authTouched && _documentAuth is not null && _mode == "document")
        {
            _authValue = "doc:";
        }
        else if (!_authValue.StartsWith("preset:", StringComparison.Ordinal))
        {
            _authValue = $"type:{_auth.GetValueOrDefault("type", "none")}";
        }
    }

    private void ChooseAuth(string value)
    {
        _authValue = value;
        _authTouched = true;
        if (value == "doc:" && _documentAuth is not null)
        {
            _auth = new(_documentAuth);
        }
        else if (value.StartsWith("preset:", StringComparison.Ordinal) && Preset is { } preset)
        {
            _auth = AuthOf(preset.Auths[int.Parse(value[7..], System.Globalization.CultureInfo.InvariantCulture)]);
        }
        else
        {
            _auth = new() { ["type"] = value[5..] };
        }
        Later();
    }

    private bool Shown(AuthSetting setting) =>
        setting.When is not { } when
        || (_auth.GetValueOrDefault(when.Setting) ?? AuthType?.Settings.FirstOrDefault(s => s.Id == when.Setting)?.Default) == when.Is;

    private void SetSetting(string id, string? value)
    {
        _auth[id] = value ?? string.Empty;
        _authTouched = true;
        Later();
    }

    private void PresetChosen(string? value)
    {
        _preset = value ?? string.Empty;
        if (Preset is { } chosen)
        {
            if (_baseUrl.Trim().Length == 0)
            {
                _baseUrl = chosen.Urls.FirstOrDefault()?.Url ?? string.Empty;
            }
            ChooseAuth("preset:0");
            if (chosen.SpecPaths.Count == 0 && _mode != "form")
            {
                _mode = "form";
            }
        }
        Later();
    }

    private void UseUrl()
    {
        _file = string.Empty;
        _pasted = string.Empty;
        Later(0);
    }

    private void Pasted(ChangeEventArgs e)
    {
        _pasted = e.Value?.ToString() ?? string.Empty;
        _file = string.Empty;
        _url = string.Empty;
        Later();
    }

    private async Task BrowseAsync()
    {
        if (await Files.ChooseAsync("file", "OpenAPI document", null, "api", [".json", ".yaml", ".yml"]) is { } path)
        {
            _file = path;
            _url = string.Empty;
            _pasted = string.Empty;
            Later(0);
        }
    }

    private void Named(ChangeEventArgs e)
    {
        _name = e.Value?.ToString() ?? string.Empty;
        _named = _name.Trim().Length > 0;
        Later();
    }

    /// <summary>Find its OpenAPI: each place the preset's host keeps one, asked in turn; none there: list the endpoints.</summary>
    private async Task FindAsync()
    {
        if (Preset is not { } chosen || Root(_baseUrl) is not { } root)
        {
            return;
        }
        foreach (var path in chosen.SpecPaths)
        {
            try
            {
                await Apis.PreviewAsync(new Dictionary<string, object?> { ["spec_url"] = root + path });
                _url = root + path;
                _mode = "document";
                UseUrl();
                return;
            }
            catch (ApiException)
            {
                // not there: the next place
            }
        }
        _said = "No OpenAPI document there: list the endpoints.";
        _mode = "form";
    }

    [GeneratedRegex("^(https?://[^/]+)")]
    private static partial Regex SiteRoot();

    public void Dispose()
    {
        _waiting?.Cancel();
        _waiting?.Dispose();
    }
}
