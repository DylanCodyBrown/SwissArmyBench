namespace SwissArmyBench.Web.Api.Apis;

/// <summary>One operation an API's refresh adds, removes or changes.</summary>
public sealed record ApiDiffRow(string Id, string Method, string Path, IReadOnlyList<string>? Changes = null);
