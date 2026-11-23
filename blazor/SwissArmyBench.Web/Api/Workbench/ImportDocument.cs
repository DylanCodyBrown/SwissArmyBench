namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A notebook, script or app another project offers (made: a file the app writes).</summary>
public sealed record ImportDocument(string Path, string Kind, bool Made = false);
