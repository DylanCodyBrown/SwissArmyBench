namespace SwissArmyBench.Web.Api.Apis;

/// <summary>PUT /apis/{name}/calls/{operation}: the web call blade saved, and its DuckDB SQL name while Return as table is on.</summary>
public sealed record SavedWebCall(string Blade, string? SqlName, SavedConversion? WebCall = null);
