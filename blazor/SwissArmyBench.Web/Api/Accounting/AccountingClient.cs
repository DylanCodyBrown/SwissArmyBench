namespace SwissArmyBench.Web.Api.Accounting;

/// <summary>The Excel canvas's routes (the Accounting extension's routes.py): a design opened (from its file, new,
/// or as it is here), its sheets and blocks changed, Play, the built workbook's bytes, Save, Export workbook.py;
/// the templates, their bindings, and statements and invoices built from them.</summary>
public sealed class AccountingClient
{
    private readonly ApiClient _api;
    private readonly HttpClient _http;

    public AccountingClient(ApiClient api, HttpClient http)
    {
        _api = api;
        _http = http;
    }

    public Task<WorkbookState> OpenAsync(IReadOnlyDictionary<string, object?> body) => _api.PostAsync<WorkbookState>("/accounting/designs", body);

    public Task<WorkbookState> GetAsync(string id) => _api.GetAsync<WorkbookState>(Base(id));

    /// <summary>A change of the design by its route under the design (empty: the design itself).</summary>
    public Task<WorkbookState> SendAsync(string id, HttpMethod method, string route, object? body = null)
    {
        var path = Base(id) + route;
        return method.Method switch
        {
            "POST" => _api.PostAsync<WorkbookState>(path, body ?? new { }),
            "PUT" => _api.PutAsync<WorkbookState>(path, body ?? new { }),
            "PATCH" => _api.PatchAsync<WorkbookState>(path, body ?? new { }),
            "DELETE" => _api.DeleteAsync<WorkbookState>(path),
            _ => _api.GetAsync<WorkbookState>(path),
        };
    }

    public Task CloseAsync(string id) => _api.DeleteAsync(Base(id));

    public Task<ExportedWorkbook> ExportAsync(string id) => _api.PostAsync<ExportedWorkbook>(Base(id) + "/export", new { });

    /// <summary>The workbook Play built: its bytes and its name.</summary>
    public async Task<(byte[] Bytes, string? Name)> DownloadAsync(string id)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, Base(id) + "/download");
        request.Headers.Add("X-Sab-Client", ApiClient.ClientId);
        using var answer = await _http.SendAsync(request);
        if (!answer.IsSuccessStatusCode)
        {
            var text = await answer.Content.ReadAsStringAsync();
            throw new ApiException((int)answer.StatusCode, ApiClient.ReadRefusal(text, answer.StatusCode), text);
        }
        var name = answer.Content.Headers.ContentDisposition?.FileNameStar ?? answer.Content.Headers.ContentDisposition?.FileName?.Trim('"');
        return (await answer.Content.ReadAsByteArrayAsync(), name);
    }

    public Task<TemplateList> TemplatesAsync() => _api.PostAsync<TemplateList>("/accounting/templates", new { });

    public Task<WorkbookTemplate> ImportTemplateAsync(string source) => _api.PostAsync<WorkbookTemplate>("/accounting/templates/import", new { source });

    public Task<WorkbookTemplate> ShowTemplateAsync(string name) => _api.PostAsync<WorkbookTemplate>("/accounting/templates/show", new { name });

    public Task<WorkbookTemplate> BindAsync(IReadOnlyDictionary<string, object?> body) => _api.PostAsync<WorkbookTemplate>("/accounting/templates/bind", body);

    public Task<BuildPlan> BuildAsync(IReadOnlyDictionary<string, object?> body) => _api.PostAsync<BuildPlan>("/accounting/build", body);

    /// <summary>The open tables' names (GET /datasets): what a block reads.</summary>
    public async Task<IReadOnlyList<string>> OpenTablesAsync()
    {
        var found = await _api.GetAsync<System.Text.Json.JsonElement>("/datasets");
        return found.TryGetProperty("datasets", out var list)
            ? list.EnumerateArray().Select(d => d.TryGetProperty("name", out var n) ? n.GetString() ?? string.Empty : string.Empty).Where(n => n.Length > 0).ToList()
            : [];
    }

    public Task RegisterAsync() => _api.PostAsync("/accounting/register", new { open = true });

    private static string Base(string id) => $"/accounting/designs/{Uri.EscapeDataString(id)}";
}
