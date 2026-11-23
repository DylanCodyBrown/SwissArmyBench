using System.Text.Json;

namespace SwissArmyBench.Web.Api.Apis;

/// <summary>Where an API is hosted (an Azure Function App, AWS Lambda, Google): its addresses, sign-ins and document paths.</summary>
public sealed record ApiPreset(
    string Id,
    string Label,
    IReadOnlyList<PresetUrl> Urls,
    IReadOnlyList<IReadOnlyDictionary<string, JsonElement>> Auths,
    IReadOnlyList<string> SpecPaths);
