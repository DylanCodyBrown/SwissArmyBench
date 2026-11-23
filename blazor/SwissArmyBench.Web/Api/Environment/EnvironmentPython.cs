namespace SwissArmyBench.Web.Api.Environment;

/// <summary>The project's own Python, in one line (its .venv: making, ready, failed).</summary>
public sealed record EnvironmentPython(string Status, string Words);
