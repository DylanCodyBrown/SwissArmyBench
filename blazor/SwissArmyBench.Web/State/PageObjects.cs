using SwissArmyBench.Web.Api.Collaboration;

namespace SwissArmyBench.Web.State;

/// <summary>
/// What the page in front shows, as the objects a note can name (the owner, 2026-11-25: the `@` picker "should
/// recognize the objects on page"): the Tables page's table and its columns, the open notebook and its cells, the
/// open script and its functions, a connection on its page. Each page sets it as what it shows changes and clears
/// it as it leaves; the Collaboration panel's `@` offers these first and its "This page" filter keeps their threads.
/// Its value raises one Changed.
/// </summary>
public sealed class PageObjects
{
    private string _key = string.Empty;

    public event Action? Changed;

    public IReadOnlyList<CollabReference> Objects { get; private set; } = [];

    /// <summary>The page's objects' paths and names, each once (what "This page" sends the server).</summary>
    public IReadOnlyList<string> Paths => Objects.Select(o => o.Path).Distinct(StringComparer.Ordinal).ToList();

    /// <summary>The page shows these now (the same list again changes nothing).</summary>
    public void Set(IReadOnlyList<CollabReference> objects)
    {
        var key = string.Join('\n', objects.Select(o => $"{o.Kind}:{o.Path}#{o.Id}:{o.Text}"));
        if (key == _key)
        {
            return;
        }
        _key = key;
        Objects = objects;
        Changed?.Invoke();
    }

    /// <summary>A page leaving clears what it set (another page's list stays).</summary>
    public void Clear(string? path = null)
    {
        if (path is null || Objects.Any(o => o.Path == path))
        {
            Set([]);
        }
    }
}
