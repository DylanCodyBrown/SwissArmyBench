using System.Text.Json;

using SwissArmyBench.Web.Api;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A run's failure: its sentence, the file's line it points at, and the source's own words.</summary>
public sealed record SqlFailure(string Words, int? Line, string? Details)
{
    public static SqlFailure Of(ApiException error)
    {
        int? line = null;
        try
        {
            using var body = JsonDocument.Parse(error.Body);
            if (body.RootElement.ValueKind == JsonValueKind.Object && body.RootElement.TryGetProperty("line", out var at) && at.ValueKind == JsonValueKind.Number)
            {
                line = at.GetInt32();
            }
        }
        catch (JsonException)
        {
            // a refusal in words only: no line to mark
        }
        return new SqlFailure(error.Refusal.Error, line, error.Refusal.Details);
    }
}
