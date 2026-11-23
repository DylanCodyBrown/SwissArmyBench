namespace SwissArmyBench.Web.State;

/// <summary>
/// The command palette's list (Ctrl+Shift+P) and the keyboard shortcuts sheet (?): a page in front gives its commands
/// (the classic setCommandSource); the app's own (Help) are always there; the ones used last come first. The layout
/// draws the palette or the sheet while one is open.
/// </summary>
public sealed class Commands
{
    // The recently used commands kept first, at most this many.
    private const int Remembered = 8;

    private readonly List<string> _recent = [];
    private Func<IReadOnlyList<PaletteCommand>>? _page;

    public event Action? Changed;

    /// <summary>Whether the page in front offers Find data (Ctrl+K): the grid page.</summary>
    public bool FindData { get; set; }

    /// <summary>"palette", "shortcuts", "find" (the page's Find data), or null when none is open.</summary>
    public string? Open { get; private set; }

    /// <summary>The page in front's commands (null: none), set as it opens and cleared as it closes.</summary>
    public void SetPageCommands(Func<IReadOnlyList<PaletteCommand>>? page)
    {
        _page = page;
    }

    public void Show(string which)
    {
        Open = which;
        Changed?.Invoke();
    }

    public void Close()
    {
        Open = null;
        Changed?.Invoke();
    }

    /// <summary>Every command, the recently used first, then the page's, then the app's.</summary>
    public IReadOnlyList<PaletteCommand> All()
    {
        var all = (_page?.Invoke() ?? []).Concat(Help()).ToList();
        return all
            .OrderBy(c => _recent.IndexOf(c.Id) is var at && at >= 0 ? at : int.MaxValue)
            .ToList();
    }

    public async Task RunAsync(PaletteCommand command)
    {
        Close();
        if (command.WhyNot is not null)
        {
            return;
        }
        _recent.Remove(command.Id);
        _recent.Insert(0, command.Id);
        if (_recent.Count > Remembered)
        {
            _recent.RemoveAt(_recent.Count - 1);
        }
        await command.Run();
    }

    private IEnumerable<PaletteCommand> Help() =>
    [
        new("help.palette", "Help", "Show every command", () => { Show("palette"); return Task.CompletedTask; }, "Ctrl+Shift+P"),
        new("help.shortcuts", "Help", "Keyboard shortcuts", () => { Show("shortcuts"); return Task.CompletedTask; }, "?"),
    ];
}
