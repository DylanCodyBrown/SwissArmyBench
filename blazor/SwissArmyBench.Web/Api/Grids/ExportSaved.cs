namespace SwissArmyBench.Web.Api.Grids;

/// <summary>An export saved in the export folder: where, and the server's words ("Saved 120 rows...").</summary>
public sealed record ExportSaved(string Saved, string Message);
