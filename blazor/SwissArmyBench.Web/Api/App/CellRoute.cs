namespace SwissArmyBench.Web.Api.App;

/// <summary>A cell kind another kernel runs, as the open project's mode declares it (MODE cell_routes; the classic
/// modes.ts CellRoute): its name and editor language, and the routes that run it (one output record a line), draw
/// it (a TSX cell's page), open a table result as a grid, give its declarations to the editor and install a tool
/// it needs. A route the mode leaves out is empty.</summary>
public sealed record CellRoute(
    string Name,
    string Language,
    string Run = "",
    string? Grid = null,
    string? Preview = null,
    string? Types = null,
    string? Install = null);
