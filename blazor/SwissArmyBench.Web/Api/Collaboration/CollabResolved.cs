namespace SwissArmyBench.Web.Api.Collaboration;

/// <summary>A thread's resolve: by whom (a login) and when.</summary>
public sealed record CollabResolved(string By, string Time);
