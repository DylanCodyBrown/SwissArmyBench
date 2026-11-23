namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /blades/inspect: a code's settings and passwords read again (with ast, never run), and the packages it needs.</summary>
public sealed record InspectedCode(
    IReadOnlyList<FormField> Settings,
    IReadOnlyList<string> Secrets,
    string? InstallHere = null,
    IReadOnlyList<PackageNeed>? Packages = null,
    MissingPackages? Missing = null);
