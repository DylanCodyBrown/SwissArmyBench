using System.Text.Json;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Collaboration;
using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.State;

/// <summary>
/// The Collaboration panel's state on this page (the owner, 2026-11-25): whether the panel is open, the place it shows
/// (a channel or an object's threads), the unread counts for the top corner's icon, and the page in front's objects
/// (PageObjects: the `@` list's first lines and the filter "This page"). It follows the collaboration_changed,
/// collaboration_unread and collaboration_show notices, and collaboration_news (a project opened, a Pull's files:
/// "3 new messages from Sam and Avery", said once in the corner with Open). Its value raises one Changed.
/// </summary>
public sealed class CollaborationState : IDisposable
{
    public const string ChangedNotice = "collaboration_changed";
    public const string UnreadNotice = "collaboration_unread";
    public const string ShowNotice = "collaboration_show";
    public const string NewsNotice = "collaboration_news";
    public const string CollaborateWords = "Collaborate";
    public const string CellKind = "cell";

    private readonly CollaborationClient _client;
    private readonly LiveUpdates _live;
    private readonly ProjectState _project;
    private readonly PageObjects _shown;
    private readonly Notes _notes;
    private string? _projectPath;

    public CollaborationState(CollaborationClient client, LiveUpdates live, ProjectState project, PageObjects shown, Notes notes)
    {
        _client = client;
        _live = live;
        _project = project;
        _shown = shown;
        _notes = notes;
        _live.NoticeArrived += OnNotice;
        _project.Changed += OnProject;
        _shown.Changed += OnShown;
    }

    public event Action? Changed;

    public bool Open { get; private set; }

    /// <summary>The place shown: "#general", "#month-end", an object's key ("cell:data.ipynb#7"), or null for all.</summary>
    public string? Where { get; private set; }

    /// <summary>The object a Collaborate click named: a new thread there is anchored to it.</summary>
    public CollabReference? Anchor { get; private set; }

    public int Unread { get; private set; }

    public int Mentions { get; private set; }

    /// <summary>Counts each collaboration_changed (the panel reads its timeline and thread again when it moves).</summary>
    public int Version { get; private set; }

    /// <summary>The thread to open when the panel next draws (a click on a search result, a notice), or null.</summary>
    public string? OpenThread { get; private set; }

    /// <summary>The page in front's objects' paths and names as the server reads them (a JSON list), or null.</summary>
    public string? Page => _shown.Paths is { Count: > 0 } paths ? JsonSerializer.Serialize(paths) : null;

    /// <summary>The page in front's objects (the `@` list's first lines).</summary>
    public IReadOnlyList<CollabReference> PageObjects => _shown.Objects;

    /// <summary>Counts each unread count that went up (the icon's small wiggle).</summary>
    public int Arrivals { get; private set; }

    public async Task StartAsync()
    {
        try
        {
            TakeCounts(await _client.UnreadAsync());
        }
        catch (ApiException)
        {
            // An older server: the panel says so when it opens.
        }
    }

    public void Toggle()
    {
        Open = !Open;
        Changed?.Invoke();
    }

    public void SetOpen(bool open)
    {
        if (Open == open)
        {
            return;
        }
        Open = open;
        Changed?.Invoke();
    }

    /// <summary>Collaborate on an object (a cell's menu, a tab's menu, a connection): the panel opens on its threads.</summary>
    public void Show(CollabReference anchor)
    {
        Anchor = anchor;
        Where = KeyOf(anchor);
        OpenThread = null;
        Open = true;
        Changed?.Invoke();
    }

    /// <summary>A menu's Collaborate line on an object (a cell's menu, a tab's menu): the panel opens on its threads.</summary>
    public MenuEntry Entry(CollabReference anchor, string? disabled = null) => new(CollaborateWords, "chat", () =>
    {
        Show(anchor);
        return Task.CompletedTask;
    }, disabled);

    /// <summary>A file of the project as an object: a notebook, a .sql file or a script (by its name).</summary>
    public static CollabReference FileAnchor(string path) =>
        new(path.EndsWith(".ipynb", StringComparison.OrdinalIgnoreCase) ? "notebook"
            : path.EndsWith(".sql", StringComparison.OrdinalIgnoreCase) ? "sql" : "script",
            path, string.Empty, FilePaths.Name(path));

    /// <summary>A channel or an object's key, or null for every thread.</summary>
    public void Go(string? where)
    {
        Where = string.IsNullOrEmpty(where) ? null : where;
        if (Where is null || Where.StartsWith('#'))
        {
            Anchor = null;
        }
        Changed?.Invoke();
    }

    public void OpenThreadOnce(string? thread)
    {
        OpenThread = thread;
        Open = true;
        Changed?.Invoke();
    }

    /// <summary>The thread asked for was opened.</summary>
    public void TookThread() => OpenThread = null;

    public void TakeCounts(CollabUnread counts)
    {
        Arrivals += counts.Total > Unread ? 1 : 0;
        Unread = counts.Total;
        Mentions = counts.Mentions;
        Changed?.Invoke();
    }

    /// <summary>A reference's key, as the server makes it: kind:path#id.</summary>
    public static string KeyOf(CollabReference reference) =>
        $"{reference.Kind}:{reference.Path}" + (string.IsNullOrEmpty(reference.Id) ? string.Empty : $"#{reference.Id}");

    private void OnNotice(Notice notice)
    {
        switch (notice.Type)
        {
            case ChangedNotice:
                Version++;
                Changed?.Invoke();
                break;
            case UnreadNotice:
                TakeCounts(new CollabUnread((int)(notice.Number("total") ?? 0), (int)(notice.Number("mentions") ?? 0)));
                break;
            case NewsNotice when notice.Text("words") is { Length: > 0 } words:
                _ = _notes.SayAsync(words, "Open", () =>
                {
                    Go(null);
                    OpenThreadOnce(notice.Text("thread") is { Length: > 0 } thread ? thread : null);
                    return Task.CompletedTask;
                });
                break;
            case ShowNotice:
                Where = notice.Text("where") is { Length: > 0 } where ? where : null;
                Anchor = notice.Body.TryGetProperty("anchor", out var anchor) && anchor.ValueKind == JsonValueKind.Object
                    ? anchor.Deserialize<CollabReference>(ApiClient.Json)
                    : null;
                Open = true;
                Changed?.Invoke();
                break;
            default:
                break;
        }
    }

    private void OnProject()
    {
        var path = _project.Current?.Path;
        if (path == _projectPath)
        {
            return;
        }
        _projectPath = path;
        Version++;
        _ = StartAsync();
    }

    private void OnShown() => Changed?.Invoke();

    public void Dispose()
    {
        _live.NoticeArrived -= OnNotice;
        _project.Changed -= OnProject;
        _shown.Changed -= OnShown;
    }
}
