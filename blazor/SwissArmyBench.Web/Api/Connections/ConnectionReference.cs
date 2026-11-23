namespace SwissArmyBench.Web.Api.Connections;

/// <summary>A place a connection is named: a notebook's cell, a script, a canvas, an open grid.</summary>
public sealed record ConnectionReference(string Kind, string Title, string Document = "", int? Cell = null, string How = "", string Line = "", string? Grid = null);
