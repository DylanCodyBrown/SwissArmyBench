namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>
/// What an editor's intelligence request carries beside its text (POST /workbench/intel/*): the kernel and document,
/// and for a notebook cell the other cells' text, so a name made above is known. codeEditor.js asks for it on each
/// request, then sends it straight to the server.
/// </summary>
public sealed record IntelContext(
    string? Kernel,
    string? Path,
    string? Python,
    bool Notebook,
    IReadOnlyList<string> Before,
    IReadOnlyList<string> After,
    string Document,
    string? Connection);
