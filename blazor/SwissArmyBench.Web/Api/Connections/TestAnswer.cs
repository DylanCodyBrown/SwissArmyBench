namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /connections/test: what the form's code made, when it worked.</summary>
public sealed record TestAnswer(string? Type = null, string? Found = null, string? Name = null, string? PreviewError = null);
