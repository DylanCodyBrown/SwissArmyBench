namespace SwissArmyBench.Web.Api.Apis;

/// <summary>One setting of a sign-in type: a box, or a choice; shown only when another setting is a value.</summary>
public sealed record AuthSetting(
    string Id,
    string Label,
    string Default,
    IReadOnlyList<AuthChoice> Choices,
    AuthWhen? When);
