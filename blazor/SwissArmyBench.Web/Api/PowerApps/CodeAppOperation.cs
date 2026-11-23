namespace SwissArmyBench.Web.Api.PowerApps;

/// <summary>One operation of a connector: its method, path, inputs, body and answers.</summary>
public sealed record CodeAppOperation
{
    public string Id { get; init; } = string.Empty;

    public string OperationId { get; init; } = string.Empty;

    public string Name { get; init; } = string.Empty;

    public string Method { get; init; } = string.Empty;

    public string Path { get; init; } = string.Empty;

    public string Description { get; init; } = string.Empty;

    public IReadOnlyList<string> Tags { get; init; } = [];

    public IReadOnlyList<CodeAppParameter> Parameters { get; init; } = [];

    public CodeAppBody? Body { get; init; }

    public IReadOnlyList<CodeAppResponse> Responses { get; init; } = [];
}
