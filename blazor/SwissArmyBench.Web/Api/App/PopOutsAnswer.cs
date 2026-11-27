namespace SwissArmyBench.Web.Api.App;

/// <summary>GET /pop-outs and the pop_outs notice: everything in a window of its own, how many main windows are
/// open, and what was just brought back (the notice's).</summary>
public sealed record PopOutsAnswer(IReadOnlyList<PopOutEntry> Popped, int Mains, PopOutEntry? Reattached = null);
