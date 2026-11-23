namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>POST /local-api/export: the folder, its files, the ones written and kept, the variables to set where it runs.</summary>
public sealed record ExportedApi(
    ExportTarget Target,
    string Folder,
    IReadOnlyList<string> Files,
    IReadOnlyList<string> Written,
    IReadOnlyList<KeptFile> Kept,
    IReadOnlyList<string> Variables,
    IReadOnlyList<string>? Warnings = null);
