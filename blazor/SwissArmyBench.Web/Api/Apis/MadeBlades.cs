namespace SwissArmyBench.Web.Api.Apis;

/// <summary>POST /apis/{name}/make-into-blades: its web call blades.</summary>
public sealed record MadeBlades(IReadOnlyList<string> WebCalls);
