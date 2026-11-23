namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A Python a loose document's kernel can run in (GET /workbench/pythons: this server's own first).</summary>
public sealed record PythonChoice(string Python, string? Version, bool Ipykernel);
