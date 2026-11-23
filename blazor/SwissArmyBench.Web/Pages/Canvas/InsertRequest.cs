namespace SwissArmyBench.Web.Pages.Canvas;

/// <summary>A widget put on the page: into a container (null: the page), at a place (null: where the server puts it).</summary>
public sealed record InsertRequest(string Widget, string? Parent, double? X, double? Y);
