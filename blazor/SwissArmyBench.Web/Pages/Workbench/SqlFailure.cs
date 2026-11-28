using System.Text.Json;

using SwissArmyBench.Web.Api;

namespace SwissArmyBench.Web.Pages.Workbench;

/// <summary>A run's failure: its sentence, the file's line it points at, and the source's own words;
/// <c>AddConnection</c>: a Power Query's source no saved connection matches (the page offers Add connection).</summary>
public sealed record SqlFailure(string Words, int? Line, string? Details, bool AddConnection = false)
{
    public static SqlFailure Of(ApiException error)
    {
        int? line = null;
        var add = false;
        try
        {
            using var body = JsonDocument.Parse(error.Body);
            if (body.RootElement.ValueKind == JsonValueKind.Object)
            {
                if (body.RootElement.TryGetProperty("line", out var at) && at.ValueKind == JsonValueKind.Number)
                {
                    line = at.GetInt32();
                }
                add = body.RootElement.TryGetProperty("add_connection", out var offered) && offered.ValueKind == JsonValueKind.True;
            }
        }
        catch (JsonException)
        {
            // a refusal in words only: no line to mark
        }
        return new SqlFailure(error.Refusal.Error, line, error.Refusal.Details, add);
    }
}
