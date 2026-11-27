using System.Net;
using System.Text;

namespace SwissArmyBench.Web.Tests;

/// <summary>A made-up server that keeps every request waiting until <see cref="Release"/>: what was asked meanwhile
/// is counted (a button pressed twice before the first answer came).</summary>
public sealed class HeldServer : HttpMessageHandler
{
    private readonly TaskCompletionSource _gate = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly string _json;

    public HeldServer(string json)
    {
        _json = json;
    }

    public List<string> Asked { get; } = [];

    public void Release() => _gate.TrySetResult();

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        Asked.Add($"{request.Method} {request.RequestUri?.AbsolutePath}");
        await _gate.Task;
        return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(_json, Encoding.UTF8, "application/json") };
    }
}
