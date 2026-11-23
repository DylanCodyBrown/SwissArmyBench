using Microsoft.JSInterop;

namespace SwissArmyBench.Web.State;

/// <summary>
/// The theme (the classic theme.ts): System, Light, Dark or the two high contrast ones, remembered by this browser
/// and never sent anywhere. The effective theme lands on html[data-theme], which tokens.css colours.
/// </summary>
public sealed class ThemeState
{
    public const string System = "system";

    /// <summary>The choices and their words, in Settings' order.</summary>
    public static readonly IReadOnlyList<(string Value, string Label)> Choices =
    [
        (System, "System"),
        ("light", "Light"),
        ("dark", "Dark"),
        ("hc-light", "High contrast light"),
        ("hc-dark", "High contrast dark"),
    ];

    private readonly IJSRuntime _js;
    private string _systemTheme = "light";
    private DotNetObjectReference<ThemeState>? _self;

    public ThemeState(IJSRuntime js)
    {
        _js = js;
    }

    public event Action? Changed;

    /// <summary>What the user chose (system, light, dark, hc-light, hc-dark).</summary>
    public string Choice { get; private set; } = System;

    /// <summary>The theme drawn: the choice, or the system's when the choice is System.</summary>
    public string Effective => Choice == System ? _systemTheme : Choice;

    public bool IsDark => Effective is "dark" or "hc-dark";

    public async Task StartAsync()
    {
        _self = DotNetObjectReference.Create(this);
        _systemTheme = await _js.InvokeAsync<string>("sab.systemTheme", _self);
        Choice = await _js.InvokeAsync<string?>("sab.recall", "theme") ?? System;
        await ApplyAsync();
    }

    public async Task SetAsync(string choice)
    {
        Choice = choice;
        await _js.InvokeVoidAsync("sab.remember", "theme", choice);
        await ApplyAsync();
    }

    [JSInvokable]
    public async Task SystemThemeChangedAsync(string theme)
    {
        _systemTheme = theme;
        await ApplyAsync();
    }

    private async Task ApplyAsync()
    {
        await _js.InvokeVoidAsync("sab.setTheme", Effective);
        Changed?.Invoke();
    }
}
