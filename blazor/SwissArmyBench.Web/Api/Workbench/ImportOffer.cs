namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /project/import/sources: what another project folder (or a loose file) offers the open project.</summary>
public sealed record ImportOffer(
    string From,
    string Kind,
    IReadOnlyList<ImportDocument> Documents,
    IReadOnlyList<ImportItem> Connections,
    IReadOnlyList<ImportItem> Blades);
