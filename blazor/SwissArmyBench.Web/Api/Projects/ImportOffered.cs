namespace SwissArmyBench.Web.Api.Projects;

/// <summary>POST /project/import/sources: what a project folder or a loose file offers.</summary>
/// <param name="From">The place's whole path ("computer": this computer's own).</param>
/// <param name="Kind">folder or file (a loose file is the one imported: no choice to make).</param>
/// <param name="Documents">Its notebooks, scripts and apps.</param>
/// <param name="Connections">Its connections.</param>
/// <param name="Blades">Its other blades.</param>
public sealed record ImportOffered(
    string From,
    string Kind,
    IReadOnlyList<ImportDocument> Documents,
    IReadOnlyList<ImportItem> Connections,
    IReadOnlyList<ImportItem> Blades);
