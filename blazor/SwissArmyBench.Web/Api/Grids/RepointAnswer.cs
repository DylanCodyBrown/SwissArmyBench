namespace SwissArmyBench.Web.Api.Grids;

/// <summary>POST /connections/{name}/repoint: how many cells now name the other connection, and the documents that
/// could not be changed.</summary>
public sealed record RepointAnswer(int Cells, IReadOnlyList<RepointFailure> Failed);
