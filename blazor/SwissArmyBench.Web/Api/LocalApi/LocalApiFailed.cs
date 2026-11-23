namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>The local sandbox API's process failed: why, and where in API.py.</summary>
public sealed record LocalApiFailed(string Error, int? Line = null);
