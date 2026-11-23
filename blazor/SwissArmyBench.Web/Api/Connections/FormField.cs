using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>One setting of a connection's code as its form shows it: where it sits in the code (Id), its name, key and value, its box's text, a picker (file, folder), suggestions.</summary>
public sealed record FormField(
    string Id,
    string Name,
    JsonElement Value,
    string Type = "text",
    bool Placeholder = false,
    string? Picker = null,
    string Key = "",
    string? Text = null,
    IReadOnlyList<FieldSuggestion>? Suggestions = null);
