namespace SwissArmyBench.Web.Components;

/// <summary>The page plug-ins (the classic pageActions.ts registry): a Blazor component registered under the id an
/// extension's PAGE_ACTIONS names. The front end is shared and an extension adds no front-end code, so its pages live
/// in the base and are registered here; a page action whose plug-in is not registered draws no button. A plug-in is
/// opened with the page's own context and an OnClose callback (as a dialog or a page of its own).</summary>
public sealed class PagePlugins
{
    private readonly Dictionary<string, Type> _plugins = new(StringComparer.Ordinal);

    /// <summary>Register <typeparamref name="TComponent"/> under <paramref name="id"/>; it takes the parameters
    /// Context (object?) and OnClose (EventCallback).</summary>
    public void Register<TComponent>(string id)
        where TComponent : Microsoft.AspNetCore.Components.IComponent => _plugins[id] = typeof(TComponent);

    /// <summary>The plug-in registered under <paramref name="id"/>, or null when it is not here.</summary>
    public Type? Find(string id) => _plugins.GetValueOrDefault(id);

    public bool Has(string id) => _plugins.ContainsKey(id);
}
