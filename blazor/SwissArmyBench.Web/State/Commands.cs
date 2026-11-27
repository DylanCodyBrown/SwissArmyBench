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

    /// <summary>The command that lists every command, and the page's own answer that only says where it is.</summary>
    public const string ListCommand = "commands";
    public const string PlaceCommand = "place";

    private readonly List<string> _recent = [];
    private Func<IReadOnlyList<PaletteCommand>>? _page;
    private Func<string, System.Text.Json.JsonElement, Task<CommandAnswer?>>? _answers;

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

    /// <summary>A page that closes takes its commands back, unless the page now in front has already given its own
    /// (a page opened is drawn before the one it replaces goes).</summary>
    public void WithdrawPageCommands(Func<IReadOnlyList<PaletteCommand>> page)
    {
        if (_page is not null && _page.Equals(page))
        {
            _page = null;
        }
    }

    /// <summary>The page in front's own answers to the commands that take arguments or give something back (the
    /// Notebooks and Scripts pages' "documents", "file.openAt"...): null from it when the command is not one of
    /// those, and the palette's command of that id runs instead. Set as the page opens, cleared as it closes.</summary>
    public void SetPageAnswers(Func<string, System.Text.Json.JsonElement, Task<CommandAnswer?>>? page)
    {
        _answers = page;
    }

    public void WithdrawPageAnswers(Func<string, System.Text.Json.JsonElement, Task<CommandAnswer?>> page)
    {
        if (_answers is not null && _answers.Equals(page))
        {
            _answers = null;
        }
    }

    /// <summary>
    /// A command the agent sent this window (the workbench_command notice), run as the palette runs it: "commands"
    /// lists every command of the page in front; the page's own answer when it has one; else the palette's command of
    /// that id. A command that cannot run now, or that the page does not have, is an InvalidOperationException
    /// carrying the reason in plain words.
    /// </summary>
    public async Task<CommandAnswer> AnswerAsync(string command, System.Text.Json.JsonElement args)
    {
        if (command == ListCommand)
        {
            return new CommandAnswer(new { commands = All().Select(c => new { id = c.Id, group = c.Group, title = c.Title, keys = c.Keys, why_not = c.WhyNot }).ToList() });
        }
        if (_answers is not null && await _answers(command, args) is { } own)
        {
            return own;
        }
        if (All().FirstOrDefault(c => c.Id == command) is not { } found)
        {
            throw new InvalidOperationException($"This page has no command \"{command}\": \"{ListCommand}\" lists them.");
        }
        if (found.WhyNot is { } why)
        {
            throw new InvalidOperationException(why);
        }
        await found.Run();
        var where = _answers is null ? null : await _answers(PlaceCommand, default);
        return new CommandAnswer(new { ran = command }, where?.Path, where?.Title, where?.Cell);
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

    /// <summary>A command of the page in front by its id, run when it can be (the desktop app's keys); false when the
    /// page has none of that id or it cannot run now.</summary>
    public async Task<bool> RunIdAsync(string id)
    {
        if (All().FirstOrDefault(c => c.Id == id) is not { WhyNot: null } command)
        {
            return false;
        }
        await RunAsync(command);
        return true;
    }

    private IEnumerable<PaletteCommand> Help() =>
    [
        new("help.palette", "Help", "Show every command", () => { Show("palette"); return Task.CompletedTask; }, "Ctrl+Shift+P"),
        new("help.shortcuts", "Help", "Keyboard shortcuts", () => { Show("shortcuts"); return Task.CompletedTask; }, "?"),
    ];
}
