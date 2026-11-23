namespace SwissArmyBench.Web.Api.Files;

/// <summary>POST /dialogs/choose: the path picked, or cancelled, busy, or unavailable (and why).</summary>
public sealed record ChooseAnswer(string? Path = null, bool Cancelled = false, bool Busy = false, string? Unavailable = null);
