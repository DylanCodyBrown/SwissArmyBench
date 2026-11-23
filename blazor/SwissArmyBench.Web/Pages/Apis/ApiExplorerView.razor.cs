using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Apis;
using SwissArmyBench.Web.Api.Structures;

namespace SwissArmyBench.Web.Pages.Apis;

public partial class ApiExplorerView
{
    private static readonly JsonSerializerOptions _indented = new() { WriteIndented = true };

    private readonly Dictionary<string, string> _inputs = [];
    private string? _body;
    private bool _sending;
    private ApiCallAnswer? _answer;
    private StructureDocument? _structure;
    private Exception? _error;
    private string? _shownFor;

    [Inject]
    private ApisClient Apis { get; set; } = default!;

    [Inject]
    private StructuresClient Structures { get; set; } = default!;

    [Parameter, EditorRequired]
    public ApiExplorer Explorer { get; set; } = default!;

    /// <summary>The operation shown (its id); none: the first.</summary>
    [Parameter]
    public string? Operation { get; set; }

    private ApiOperation? Picked => Explorer.Operations.FirstOrDefault(o => o.Id == Operation) ?? Explorer.Operations.FirstOrDefault();

    protected override void OnParametersSet()
    {
        if (Picked?.Id == _shownFor)
        {
            return;
        }
        _shownFor = Picked?.Id;
        _inputs.Clear();
        _body = null;
        _answer = null;
        _structure = null;
    }

    private string AddressOf(ApiOperation operation) => $"apis?name={Uri.EscapeDataString(Explorer.Name)}&operation={Uri.EscapeDataString(operation.Id)}";

    /// <summary>The body to start from: the operation's made-up example.</summary>
    private static string BodyExample(JsonElement body) =>
        body.TryGetProperty("example", out var example) ? Pretty(example) : "{}";

    private static string Pretty(JsonElement value) => JsonSerializer.Serialize(value, _indented);

    private async Task SendAsync()
    {
        if (Picked is not { } op)
        {
            return;
        }
        _sending = true;
        try
        {
            var body = op.Body is { } given ? JsonDocument.Parse(_body ?? BodyExample(given)).RootElement.Clone() : (JsonElement?)null;
            var inputs = _inputs.Where(i => i.Value.Length > 0).ToDictionary(i => i.Key, i => i.Value);
            _answer = await Apis.CallAsync(Explorer.Name, op.Id, inputs, body);
            _structure = _answer.Structure is { } id ? await Structures.GetAsync(id) : null;
            _error = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
        catch (JsonException)
        {
            _error = new ApiException(0, new Refusal("The body is not JSON: check its brackets and quotes."), string.Empty);
        }
        _sending = false;
    }
}
