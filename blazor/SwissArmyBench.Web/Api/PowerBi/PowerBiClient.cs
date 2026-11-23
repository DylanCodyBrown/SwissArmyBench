using System.Net.Http.Headers;
using System.Text.Json;

namespace SwissArmyBench.Web.Api.PowerBi;

/// <summary>Export to Power BI (the Power BI extension's routes.py): the plan, the export (written into the open
/// project's powerbi/, or a zip to save with no project open), a dropped report's bytes kept for the plan, and Open
/// in Power BI Desktop.</summary>
public sealed class PowerBiClient
{
    private readonly ApiClient _api;
    private readonly HttpClient _http;

    public PowerBiClient(ApiClient api, HttpClient http)
    {
        _api = api;
        _http = http;
    }

    public Task<PowerBiPlan> PlanAsync(IReadOnlyDictionary<string, object?> body) => _api.PostAsync<PowerBiPlan>("/powerbi/plan", body);

    public Task<PowerBiPlan> ExportAsync(IReadOnlyDictionary<string, object?> body) => _api.PostAsync<PowerBiPlan>("/powerbi/export", body);

    /// <summary>The export as a file to save (no project open): its bytes and its name.</summary>
    public async Task<(byte[] Bytes, string Name)> DownloadAsync(IReadOnlyDictionary<string, object?> body)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "/powerbi/export")
        {
            Content = new StringContent(JsonSerializer.Serialize(body, ApiClient.Json), System.Text.Encoding.UTF8, "application/json"),
        };
        request.Headers.Add("X-Sab-Client", ApiClient.ClientId);
        using var answer = await _http.SendAsync(request);
        if (!answer.IsSuccessStatusCode)
        {
            var text = await answer.Content.ReadAsStringAsync();
            throw new ApiException((int)answer.StatusCode, ApiClient.ReadRefusal(text, answer.StatusCode), text);
        }
        var name = answer.Content.Headers.ContentDisposition?.FileName?.Trim('"') ?? "export.zip";
        return (await answer.Content.ReadAsByteArrayAsync(), name);
    }

    /// <summary>A dropped or picked report's bytes, kept by the server for the plan.</summary>
    public async Task<UploadedReport> UploadAsync(Stream data, string name)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, "/powerbi/report") { Content = new StreamContent(data) };
        request.Content.Headers.ContentType = new MediaTypeHeaderValue("application/octet-stream");
        request.Headers.Add("X-File-Name", Uri.EscapeDataString(name));
        request.Headers.Add("X-Sab-Client", ApiClient.ClientId);
        using var answer = await _http.SendAsync(request);
        var text = await answer.Content.ReadAsStringAsync();
        if (!answer.IsSuccessStatusCode)
        {
            throw new ApiException((int)answer.StatusCode, ApiClient.ReadRefusal(text, answer.StatusCode), text);
        }
        return JsonSerializer.Deserialize<UploadedReport>(text, ApiClient.Json)!;
    }

    public Task OpenAsync(string path) => _api.PostAsync("/powerbi/open", new { path });
}
