using System.Net;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace SwissArmyBench.Web.Api;

/// <summary>
/// The page's one door to the server (the classic front end's web/src/api.ts). Every area's typed client
/// (ConnectionsClient, GridsClient...) calls these few methods. The page's cookie rides on every request (the browser
/// adds it; the token never reaches this code). A refusal is read into a <see cref="Refusal"/> and thrown as an
/// <see cref="ApiException"/>, so a page catches one type.
/// </summary>
public sealed class ApiClient
{
    /// <summary>The server's JSON: snake_case names, read into PascalCase records.</summary>
    public static readonly JsonSerializerOptions Json = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        NumberHandling = JsonNumberHandling.AllowReadingFromString,
    };

    /// <summary>This page's own id, made once per load (the classic page's clientId): a query's Cancel finds this
    /// page's own, and grid requests are counted per page.</summary>
    public static readonly string ClientId = Guid.NewGuid().ToString("N")[..10];

    private readonly HttpClient _http;

    public ApiClient(HttpClient http)
    {
        _http = http;
    }

    public Task<T> GetAsync<T>(string path, CancellationToken cancel = default) => SendAsync<T>(HttpMethod.Get, path, null, cancel);

    public Task<T> PostAsync<T>(string path, object? body = null, CancellationToken cancel = default) =>
        SendAsync<T>(HttpMethod.Post, path, body ?? new Dictionary<string, object>(), cancel);

    public Task<T> PutAsync<T>(string path, object body, CancellationToken cancel = default) => SendAsync<T>(HttpMethod.Put, path, body, cancel);

    public Task<T> PatchAsync<T>(string path, object body, CancellationToken cancel = default) => SendAsync<T>(HttpMethod.Patch, path, body, cancel);

    public Task<T> DeleteAsync<T>(string path, CancellationToken cancel = default) => SendAsync<T>(HttpMethod.Delete, path, null, cancel);

    /// <summary>A path's part (a name, an id) made safe to put in an address.</summary>
    public static string Part(string value) => Uri.EscapeDataString(value);

    /// <summary>Any answer read loosely into the refusal's shape ("message" as the words when "error" is missing).</summary>
    public static Refusal ReadRefusal(string text, HttpStatusCode status)
    {
        var fallback = $"The server refused ({(int)status}).";
        if (!text.TrimStart().StartsWith('{'))
        {
            return new Refusal(string.IsNullOrWhiteSpace(text) ? fallback : text.Trim());
        }
        try
        {
            using var parsed = JsonDocument.Parse(text);
            var root = parsed.RootElement;
            var words = TextOf(root, "error") ?? TextOf(root, "message") ?? fallback;
            List<Fix>? fixes = null;
            if (root.TryGetProperty("fixes", out var list) && list.ValueKind == JsonValueKind.Array)
            {
                fixes = list.Deserialize<List<Fix>>(Json);
            }
            var details = TextOf(root, "traceback");
            if (root.TryGetProperty("details", out var found))
            {
                details = found.ValueKind == JsonValueKind.String ? found.GetString() : found.GetRawText();
            }
            return new Refusal(words, TextOf(root, "where"), fixes, details);
        }
        catch (JsonException)
        {
            return new Refusal(text.Trim());
        }
    }

    private async Task<T> SendAsync<T>(HttpMethod method, string path, object? body, CancellationToken cancel)
    {
        using var request = new HttpRequestMessage(method, path);
        request.Headers.Add("X-Sab-Client", ClientId);
        if (body is not null)
        {
            request.Content = new StringContent(JsonSerializer.Serialize(body, Json), Encoding.UTF8, "application/json");
        }
        HttpResponseMessage answer;
        try
        {
            answer = await _http.SendAsync(request, cancel);
        }
        catch (HttpRequestException error)
        {
            var refusal = new Refusal("The app's server did not answer: it may have stopped.", path, null, error.Message);
            throw new ApiException(0, refusal, string.Empty);
        }
        using (answer)
        {
            var text = await answer.Content.ReadAsStringAsync(cancel);
            if (!answer.IsSuccessStatusCode)
            {
                throw new ApiException((int)answer.StatusCode, ReadRefusal(text, answer.StatusCode), text);
            }
            if (typeof(T) == typeof(string))
            {
                return (T)(object)text;
            }
            return string.IsNullOrWhiteSpace(text) ? default! : JsonSerializer.Deserialize<T>(text, Json)!;
        }
    }

    private static string? TextOf(JsonElement root, string name) =>
        root.TryGetProperty(name, out var value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;
}
