using System.Net;
using System.Text;

namespace SwissArmyBench.Web.Tests;

/// <summary>A made-up server for a component that reads one: each "METHOD /path" answers its canned JSON (the
/// query string left out), anything else 404; the requests are kept to be looked at.</summary>
public sealed class CannedServer : HttpMessageHandler
{
    private readonly Dictionary<string, string> _answers = new(StringComparer.Ordinal);

    public List<(string Route, string Body)> Asked { get; } = [];

    /// <summary>Answer <paramref name="route"/> ("GET /app/mode") with <paramref name="json"/>.</summary>
    public CannedServer Answer(string route, string json)
    {
        _answers[route] = json;
        return this;
    }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        var route = $"{request.Method} {request.RequestUri?.AbsolutePath}";
        var body = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
        Asked.Add((route, body));
        return _answers.TryGetValue(route, out var json)
            ? new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(json, Encoding.UTF8, "application/json") }
            : new HttpResponseMessage(HttpStatusCode.NotFound) { Content = new StringContent("{\"error\": \"Not here.\"}", Encoding.UTF8, "application/json") };
    }
}
