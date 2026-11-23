using System.Text.Json;

using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Widgets;

namespace SwissArmyBench.Web.Pages.Canvas;

public partial class EventField
{
    private readonly string _listId = $"cvs-payload-{Guid.NewGuid():N}"[..24];
    private string? _said;

    [Parameter, EditorRequired]
    public WidgetPort Port { get; set; } = new();

    [Parameter]
    public JsonElement? Given { get; set; }

    [Parameter]
    public WidgetContext? Context { get; set; }

    [Parameter]
    public bool Editable { get; set; }

    [Parameter]
    public Func<object?, Task<string>> OnWire { get; set; } = _ => Task.FromResult(string.Empty);

    private IReadOnlyList<string> Payload => Port.Fields.Select(f => f.Name).ToList();

    private IReadOnlyList<EventAction> Actions =>
        Given is { ValueKind: JsonValueKind.Object } given && given.TryGetProperty("actions", out var actions) && actions.ValueKind == JsonValueKind.Array
            ? actions.Deserialize<List<EventAction>>(ApiClient.Json) ?? []
            : [];

    protected override void OnParametersSet() => _said = null;

    private static string ActionWords(string action) => action switch
    {
        "call" => "Call an API endpoint",
        "set" => "Set a page value",
        _ => "Rerun the page",
    };

    private IReadOnlyList<string> FieldsOf(EventAction action) =>
        action.Endpoint is { } endpoint ? Context?.EndpointFields.GetValueOrDefault(endpoint) ?? [] : [];

    private string FieldHint(string field) => Payload.Contains(field)
        ? field
        : Payload.Count > 0 ? $"a field: {string.Join(", ", Payload.Take(3))}" : "a part of the payload, as values." + field;

    private static IReadOnlyList<string> PathNames(EventAction action) =>
        System.Text.RegularExpressions.Regex.Matches(action.Endpoint ?? string.Empty, @"\{(\w+)\}").Select(m => m.Groups[1].Value).ToList();

    private async Task PutAsync(IEnumerable<EventAction> actions)
    {
        var next = actions.Select(Sent).ToList();
        _said = await OnWire(next.Count > 0 ? new Dictionary<string, object?> { ["actions"] = next } : null);
    }

    /// <summary>An action as the server keeps it (only the parts its kind has).</summary>
    private static Dictionary<string, object?> Sent(EventAction action) => action.Do switch
    {
        "call" => new() { ["do"] = "call", ["endpoint"] = action.Endpoint ?? string.Empty, ["body"] = action.Body, ["params"] = action.Params },
        "set" => new() { ["do"] = "set", ["key"] = action.Key ?? string.Empty, ["value"] = action.Value ?? string.Empty },
        _ => new() { ["do"] = "rerun" },
    };

    private Task ChangeAsync(int at, Func<EventAction, EventAction> change) =>
        PutAsync(Actions.Select((a, i) => i == at ? change(a) : a));

    private Task RemoveAsync(int at) => PutAsync(Actions.Where((_, i) => i != at));

    private Task EndpointAsync(int at, string? endpoint) =>
        ChangeAsync(at, a => a with { Endpoint = endpoint ?? string.Empty, Body = JsonSerializer.SerializeToElement(string.Empty), Params = new Dictionary<string, string>() });

    private Task FieldAsync(int at, string field, string value) => ChangeAsync(at, a =>
    {
        var next = (a.Mapped ?? new Dictionary<string, string>()).Where(p => p.Key != field).ToDictionary(p => p.Key, p => p.Value);
        if (value.Length > 0)
        {
            next[field] = value;
        }
        return a with { Body = next.Count > 0 ? JsonSerializer.SerializeToElement(next) : JsonSerializer.SerializeToElement(string.Empty) };
    });

    private Task ParamAsync(int at, string name, string value) => ChangeAsync(at, a =>
        a with { Params = (a.Params ?? new Dictionary<string, string>()).Where(p => p.Key != name).Append(KeyValuePair.Create(name, value)).ToDictionary() });

    private Task AddAsync(string? kind)
    {
        var endpoints = Context?.Endpoints ?? [];
        EventAction? made = kind switch
        {
            "call" => new EventAction { Do = "call", Endpoint = endpoints.FirstOrDefault(e => !ApiActions.ReadsOnly(e)) ?? endpoints.FirstOrDefault() ?? string.Empty, Body = JsonSerializer.SerializeToElement(string.Empty) },
            "set" => new EventAction { Do = "set", Key = $"{Port.Name}_payload", Value = string.Empty },
            "rerun" => new EventAction { Do = "rerun" },
            _ => null,
        };
        return made is null ? Task.CompletedTask : PutAsync(Actions.Append(made));
    }
}
