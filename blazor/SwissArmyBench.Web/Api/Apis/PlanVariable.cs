namespace SwissArmyBench.Web.Api.Apis;

/// <summary>One environment variable the API's client reads.</summary>
public sealed record PlanVariable(string Name, bool Required, bool Secret);
