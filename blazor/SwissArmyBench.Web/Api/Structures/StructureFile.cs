namespace SwissArmyBench.Web.Api.Structures;

/// <summary>A structure file of the project (a card on the Structures page when nothing is open).</summary>
public sealed record StructureFile(
    string Name,
    string File,
    string Path,
    string Format,
    long Size = 0,
    string? Open = null);
