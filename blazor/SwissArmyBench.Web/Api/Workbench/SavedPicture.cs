namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /workbench/export-picture: where a diagram's picture was saved, and whether its bytes changed.</summary>
public sealed record SavedPicture(string Path, bool Written, string Format);
