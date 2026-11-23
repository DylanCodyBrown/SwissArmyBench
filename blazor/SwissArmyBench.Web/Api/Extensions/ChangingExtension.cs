namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>An extension being installed or removed: the app restarts with it.</summary>
public sealed record ChangingExtension(string Id, string Action);
