using System.Text.Json;

namespace SwissArmyBench.Web.Api;

/// <summary>
/// Packages a feature cannot go on without, in the server's one shape (domain/packages.py):
/// {"missing": {feature, packages, python, command}}, carried by an answer or a refusal.
/// </summary>
/// <param name="Feature">The feature in plain words ("Excel files").</param>
/// <param name="Packages">The pip packages it needs.</param>
/// <param name="Python">"app" (the app's own Python, POST /blades/install) or the path of the Python they go into.</param>
/// <param name="Command">The command that installs them, said as the Install button's title.</param>
public sealed record MissingPackages(string Feature, IReadOnlyList<string> Packages, string Python, string Command)
{
    /// <summary>The app's own Python, where connections and blades run.</summary>
    public const string AppPython = "app";

    /// <summary>"a", "a and b", "a, b and c" (the classic listed()).</summary>
    public string Listed => Packages.Count > 1
        ? $"{string.Join(", ", Packages.Take(Packages.Count - 1))} and {Packages[^1]}"
        : string.Join(string.Empty, Packages);

    /// <summary>The missing packages a refusal names, or null.</summary>
    public static MissingPackages? Of(Exception? error) => error is ApiException api ? Of(api.Body) : null;

    /// <summary>The missing packages an answer's text names ({"missing": {...}}), or null.</summary>
    public static MissingPackages? Of(string? body)
    {
        if (string.IsNullOrWhiteSpace(body) || !body.TrimStart().StartsWith('{'))
        {
            return null;
        }
        try
        {
            using var parsed = JsonDocument.Parse(body);
            return Of(parsed.RootElement);
        }
        catch (JsonException)
        {
            return null;
        }
    }

    /// <summary>The missing packages an answer names, or null.</summary>
    public static MissingPackages? Of(JsonElement answer)
    {
        if (answer.ValueKind != JsonValueKind.Object || !answer.TryGetProperty("missing", out var inner) || inner.ValueKind != JsonValueKind.Object)
        {
            return null;
        }
        var found = inner.Deserialize<MissingPackages>(ApiClient.Json);
        return found is { Packages.Count: > 0, Feature: not null, Python: not null } ? found with { Command = found.Command ?? string.Empty } : null;
    }
}
