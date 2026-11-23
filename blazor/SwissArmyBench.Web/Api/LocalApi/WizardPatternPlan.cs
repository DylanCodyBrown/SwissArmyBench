using System.Text.Json;

namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>The picked pattern: its own steps, their fields as they start, and the widgets it pairs with on the Canvas.</summary>
public sealed record WizardPatternPlan(
    string Pattern,
    string Label,
    IReadOnlyList<WizardStep> Steps,
    IReadOnlyDictionary<string, JsonElement> Fields,
    IReadOnlyList<WizardWidget> Widgets);
