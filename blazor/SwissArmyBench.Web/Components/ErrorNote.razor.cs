using System.Net;

using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Components;

public partial class ErrorNote
{
    private bool _sent;

    [Inject]
    private ApiClient Api { get; set; } = default!;

    [Inject]
    private IJSRuntime Js { get; set; } = default!;

    [Inject]
    private NavigationManager Nav { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    /// <summary>What went wrong: an ApiException (the server's refusal) or any other exception; null shows nothing.</summary>
    [Parameter]
    public Exception? Error { get; set; }

    /// <summary>Words of the page's own, instead of an exception (a warning, a check that failed).</summary>
    [Parameter]
    public string? Words { get; set; }

    /// <summary>A refusal of the page's own making (an install's failure with its output as the details).</summary>
    [Parameter]
    public Refusal? Said { get; set; }

    [Parameter]
    public bool Warning { get; set; }

    /// <summary>Try again: the work that failed, run once more.</summary>
    [Parameter]
    public EventCallback OnRetry { get; set; }

    [Parameter]
    public EventCallback OnClose { get; set; }

    [Inject]
    private PackagePrompts Packages { get; set; } = default!;

    [Inject]
    private VariableAsks Variables { get; set; } = default!;

    private Refusal? Refusal => Said ?? WithOlderFixes(Error switch
    {
        ApiException api => api.Refusal,
        null when Words is not null => new Refusal(Words),
        null => null,
        _ => ApiClient.ReadRefusal(Error.Message, HttpStatusCode.InternalServerError) with { Details = Error.ToString() },
    });

    protected override void OnParametersSet() => _sent = false;

    private async Task RunFixAsync(Fix fix)
    {
        switch (fix.Action)
        {
            case "try_again":
                await OnRetry.InvokeAsync();
                break;
            case "set_variable" when fix.Name is { Length: > 0 } name:
                await Variables.AddAsync(name);
                break;
            case "sign_in" or "open_settings":
                Nav.NavigateTo($"connections?name={Uri.EscapeDataString(fix.Connection ?? string.Empty)}");
                break;
            case "install" when MissingPackages.Of(Error) is { } missing:
                await Packages.PromptAsync(missing, force: true);
                break;
            case "install" when fix.Command is not null:
                await Js.InvokeAsync<bool>("sab.copy", fix.Command);
                await Notes.SayAsync($"Copied the command: {fix.Command}");
                break;
            default:
                break;
        }
    }

    /// <summary>Answers from before the shape named its fixes (the classic errorParts): Install now from "missing",
    /// Set it (or Set NAME, one each) from "missing_variables".</summary>
    private Refusal? WithOlderFixes(Refusal? refusal)
    {
        if (refusal is null || Error is not ApiException api)
        {
            return refusal;
        }
        var fixes = (refusal.Fixes ?? []).ToList();
        if (MissingPackages.Of(api) is { } missing && !fixes.Any(f => f.Label == "Install now"))
        {
            fixes.Add(new Fix("Install now", "install", missing.Command));
        }
        if (refusal.Fixes is not { Count: > 0 })
        {
            var unset = UnsetVariables(api.Body);
            fixes.AddRange(unset.Select(name => new Fix(unset.Count > 1 ? $"Set {name}" : "Set it", "set_variable", Name: name)));
        }
        return fixes.Count == (refusal.Fixes?.Count ?? 0) ? refusal : refusal with { Fixes = fixes };
    }

    private static List<string> UnsetVariables(string body)
    {
        if (!body.TrimStart().StartsWith('{'))
        {
            return [];
        }
        try
        {
            using var parsed = System.Text.Json.JsonDocument.Parse(body);
            return parsed.RootElement.TryGetProperty("missing_variables", out var names) && names.ValueKind == System.Text.Json.JsonValueKind.Array
                ? names.EnumerateArray().Where(n => n.ValueKind == System.Text.Json.JsonValueKind.String).Select(n => n.GetString()!).ToList()
                : [];
        }
        catch (System.Text.Json.JsonException)
        {
            return [];
        }
    }

    private async Task SendToAgentAsync()
    {
        var refusal = Refusal;
        if (refusal is null)
        {
            return;
        }
        await Api.PostAsync<object>("/agent/inbox", new { kind = "error", title = refusal.Error, text = refusal.Details ?? refusal.Error, note = refusal.Where ?? string.Empty });
        _sent = true;
    }

    private async Task CopyDetailsAsync()
    {
        if (await Js.InvokeAsync<bool>("sab.copy", Refusal?.Details ?? string.Empty))
        {
            await Notes.SayAsync("Copied.");
        }
    }
}
