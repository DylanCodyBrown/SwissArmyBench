namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>A problem with API.py at its line.</summary>
public sealed record LocalApiProblem(int Line, string Message);
