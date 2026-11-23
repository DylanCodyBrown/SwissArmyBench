namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>
/// The Scripts page's debugger (routes_debugger.py, over the kernel's own debugpy): a script run under it with its
/// breakpoints, the breakpoints changed while it runs, the steps, a frame's variables, an expression evaluated, stop.
/// </summary>
public sealed class DebugClient
{
    private readonly ApiClient _api;

    public DebugClient(ApiClient api)
    {
        _api = api;
    }

    public Task<DebugState> StateAsync(string kernel) => _api.GetAsync<DebugState>($"/workbench/debug?kernel={Uri.EscapeDataString(kernel)}");

    public Task<DebugState> StartAsync(string kernel, string? document, string code, IReadOnlyList<DebugBreakpoint> breakpoints) =>
        _api.PostAsync<DebugState>("/workbench/debug/start", new { kernel, document, code, breakpoints });

    public Task BreakpointsAsync(string kernel, IReadOnlyList<DebugBreakpoint> breakpoints) =>
        _api.PostAsync("/workbench/debug/breakpoints", new { kernel, breakpoints });

    /// <summary>over, into, out or continue.</summary>
    public Task StepAsync(string kernel, string action) => _api.PostAsync("/workbench/debug/step", new { kernel, action });

    public Task<DebugScopes> ScopesAsync(string kernel, int frame) => _api.PostAsync<DebugScopes>("/workbench/debug/variables", new { kernel, frame });

    public Task<DebugScopes> PartsAsync(string kernel, int reference) => _api.PostAsync<DebugScopes>("/workbench/debug/variables", new { kernel, reference });

    public Task<DebugEvaluated> EvaluateAsync(string kernel, string expression, int? frame) =>
        _api.PostAsync<DebugEvaluated>("/workbench/debug/evaluate", new { kernel, expression, frame });

    public Task<DebugState> StopAsync(string kernel) => _api.PostAsync<DebugState>("/workbench/debug/stop", new { kernel });
}
