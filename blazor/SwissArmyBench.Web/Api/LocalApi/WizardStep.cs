using System.Text.Json;

namespace SwissArmyBench.Web.Api.LocalApi;

/// <summary>One of a pattern's steps: a column, columns, a choice, a word, the other table, the totals or the columns an action sets.</summary>
public sealed record WizardStep(
    string Id,
    string Label,
    string Kind,
    string Help,
    bool Required,
    IReadOnlyList<WizardChoice> Choices,
    IReadOnlyList<string> Options,
    JsonElement? Value = null);
