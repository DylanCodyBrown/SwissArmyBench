namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>One request of the local sandbox API's log.</summary>
public sealed record LocalApiRequest(
    string At,
    string Method,
    string Path,
    int Status,
    double Ms,
    long? Rows = null,
    string? Error = null,
    int? Line = null);
