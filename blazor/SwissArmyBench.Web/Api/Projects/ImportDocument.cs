namespace SwissArmyBench.Web.Api.Projects;

/// <summary>A notebook, script or app another place offers to import.</summary>
/// <param name="Path">Its path there.</param>
/// <param name="Kind">notebook, script or app.</param>
/// <param name="Made">A file the app makes (data.py): imported as it is.</param>
public sealed record ImportDocument(string Path, string Kind, bool Made = false);
