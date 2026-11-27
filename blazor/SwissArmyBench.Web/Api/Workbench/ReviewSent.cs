namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /agent/inbox/review's answer: how many comments went as the one message, and how many secret
/// values the server masked in it.</summary>
public sealed record ReviewSent(int Comments, int Masked);
