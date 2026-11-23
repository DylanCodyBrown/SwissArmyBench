namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>The wizard's pattern that made an endpoint (API.py's marker comment).</summary>
public sealed record EndpointPattern(string Id, string Label, string Of, string Role = "");
