namespace SwissArmyBench.Web.Api.Apis;

/// <summary>A rename offered once: from, to, in words.</summary>
public sealed record ActionOffer(string From, string To, string Said);
