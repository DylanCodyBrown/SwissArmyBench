using System.Text.Json;

namespace SwissArmyBench.Web.Api.Blades;

/// <summary>A field of a blade's header (Properties): its key, label, type (text, textarea, tags, bool, choice,
/// number, names, mapping, code, readonly), value, whether it may change, its hint and its choices.</summary>
public sealed record BladeField(
    string Key,
    string Label,
    string Type,
    JsonElement Value,
    bool ReadOnly = false,
    string? Hint = null,
    IReadOnlyList<string>? Choices = null);
