namespace SwissArmyBench.Web.Api.Apis;

/// <summary>One sign-in type and the settings it takes.</summary>
public sealed record AuthKind(string Id, string Label, IReadOnlyList<AuthSetting> Settings);
