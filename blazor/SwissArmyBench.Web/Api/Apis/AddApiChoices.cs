namespace SwissArmyBench.Web.Api.Apis;

/// <summary>GET /apis/choices: Add API's sign-in types, the hosts it knows (presets) and the methods an endpoint may use.</summary>
public sealed record AddApiChoices(
    IReadOnlyList<AuthKind> AuthTypes,
    IReadOnlyList<ApiPreset> Presets,
    IReadOnlyList<string> Methods);
