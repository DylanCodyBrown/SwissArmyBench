namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>One endpoint of API.py: its method and path, its line, its words, its inputs, the data it reads, its pattern, Try it's request.</summary>
public sealed record LocalEndpoint(
    string Name,
    string Method,
    string Path,
    int Line,
    string Summary,
    IReadOnlyList<EndpointParam> Params,
    IReadOnlyList<string> Data,
    string Returns = "",
    bool Writes = false,
    EndpointPattern? Pattern = null,
    EndpointTry? Try = null);
