namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>A Power Query file's export (POST /scripts/pq/export): the folder written and its files (the file itself,
/// duckpq.py, run.py, requirements.txt, README.md), so its M runs with no app.</summary>
public sealed record PowerQueryExport(string Folder, IReadOnlyList<string> Files);
