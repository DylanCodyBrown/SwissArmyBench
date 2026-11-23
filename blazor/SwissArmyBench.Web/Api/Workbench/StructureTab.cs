using System.Text.Json;

namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A structure as its tab beside the code reads it (routes_structures.py, view=file): its file's text and
/// value (or, through its steps, the steps' result), the text's parse error, its steps, its hash; a Save's answer
/// adds what it wrote and a warning (a text that does not parse is saved all the same).</summary>
public sealed record StructureTab(
    string Id,
    string Name,
    string Format,
    string? Path,
    string? Text,
    JsonElement? Value,
    string? Hash,
    string? TextError,
    IReadOnlyList<StructureStep>? Steps,
    string? Error,
    string? Written,
    string? Warning);
