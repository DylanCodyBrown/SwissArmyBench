using System.Text.Json;

namespace SwissArmyBench.Web.Api.Structures;

/// <summary>A structure as the Structures page shows it (GET /structures/{id}): its value, its text as typed (its error), its steps and their result's text.</summary>
public sealed record StructureShown(
    string Id,
    string Name,
    string Format,
    StructureOrigin Origin,
    IReadOnlyList<StructureStep> Steps,
    string? Path = null,
    bool CanRedo = false,
    bool Dirty = false,
    long Nodes = 0,
    string? Error = null,
    JsonElement? Value = null,
    string? Text = null,
    string? TextError = null,
    string? ResultText = null,
    long Version = 0);
