using System.Text.Json;

using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Widgets;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Pages.Widgets;

public partial class WidgetProperties
{
    // The name is checked this long after typing stops.
    private const int CheckMs = 150;

    private string _name = string.Empty;
    private string _description = string.Empty;
    private string _nameLine = string.Empty;
    private string? _nameState;
    private string? _shownFor;
    private Exception? _error;
    private UpgradePlan? _plan;
    private Exception? _upgradeError;
    private CancellationTokenSource? _checkWait;
    private Task _committing = Task.CompletedTask;

    [Inject]
    private WidgetsClient Widgets { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Parameter, EditorRequired]
    public WidgetFull Widget { get; set; } = new();

    /// <summary>The code as it is in the editor now (a value is checked and written against it).</summary>
    [Parameter]
    public string Code { get; set; } = string.Empty;

    [Parameter]
    public WidgetContext? Context { get; set; }

    [Parameter]
    public EventCallback<WidgetFull> OnSaved { get; set; }

    [Parameter]
    public EventCallback<WidgetFull> OnRenamed { get; set; }

    [Parameter]
    public EventCallback OnDeleted { get; set; }

    /// <summary>A save waiting is done first (before a property or the header is written).</summary>
    [Parameter]
    public Func<Task> OnFlush { get; set; } = () => Task.CompletedTask;

    private IReadOnlyDictionary<string, JsonElement> Defaults => Widget.Properties.ToDictionary(p => p.Name, p => p.Default);

    protected override void OnParametersSet()
    {
        if (_shownFor != Widget.Name)
        {
            (_shownFor, _name, _description, _nameLine) = (Widget.Name, Widget.Name, Widget.Description, string.Empty);
        }
    }

    private static IEnumerable<(string Section, string Title, IReadOnlyList<WidgetPort> Ports, string Kind)> Sections(WidgetContract c) =>
        new[] { ("inputs", "Inputs", c.Ins, "in"), ("outputs", "Outputs", c.Outs, "out"), ("events", "Events", c.Events, "event") }
            .Where(s => s.Item3.Count > 0);

    private async Task NameTypedAsync(ChangeEventArgs e)
    {
        _name = e.Value as string ?? string.Empty;
        _checkWait?.Cancel();
        var wait = _checkWait = new CancellationTokenSource();
        try
        {
            await Task.Delay(CheckMs, wait.Token);
        }
        catch (TaskCanceledException)
        {
            return;
        }
        await CheckNameAsync();
    }

    private async Task<bool> CheckNameAsync()
    {
        var said = await Widgets.CheckNameAsync(_name, Widget.Name);
        _nameLine = _name == Widget.Name ? string.Empty : said.Said; // a rename may have landed meanwhile
        _nameState = said.State;
        return said.Ok;
    }

    private Task NameKeyAsync(KeyboardEventArgs e) => e.Key == "Enter" ? CommitAsync() : Task.CompletedTask;

    /// <summary>Enter sends the header and so does the change that follows: one at a time, the second sees the
    /// first's answer.</summary>
    private Task CommitAsync() => _committing = _committing.ContinueWith(_ => InvokeAsync(CommitOnceAsync), TaskScheduler.Default).Unwrap();

    private async Task CommitOnceAsync()
    {
        if (Widget.Prebuilt)
        {
            return;
        }
        var changes = new Dictionary<string, string>();
        if (_name != Widget.Name)
        {
            if (!await CheckNameAsync())
            {
                return;
            }
            changes["name"] = _name;
        }
        if (_description.Trim() != Widget.Description)
        {
            changes["description"] = _description;
        }
        if (changes.Count == 0)
        {
            return;
        }
        await OnFlush();
        try
        {
            var after = await Widgets.HeaderAsync(Widget.Name, changes);
            _nameLine = string.Empty;
            _shownFor = after.Name;
            await OnRenamed.InvokeAsync(after);
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    /// <summary>A default checked first (what is wrong and its fix under the box), then written into only its own
    /// characters of the code.</summary>
    private async Task<string> SetDefaultAsync(string property, object? value)
    {
        var body = new Dictionary<string, object?> { ["code"] = Code, ["property"] = property, ["value"] = value, ["values"] = Defaults };
        var checkedValue = await Widgets.CheckValueAsync(body);
        if (!checkedValue.Ok)
        {
            return $"{checkedValue.Said ?? string.Empty} {checkedValue.Fix ?? string.Empty}".Trim();
        }
        await OnFlush();
        var after = await Widgets.SetPropertyAsync(Widget.Name, body);
        await OnSaved.InvokeAsync(after);
        return string.Empty;
    }

    private async Task UpgradePreviewAsync()
    {
        try
        {
            await OnFlush();
            _plan = await Widgets.UpgradePreviewAsync(Widget.Name);
            _upgradeError = null;
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }

    private async Task UpgradeAsync()
    {
        try
        {
            var done = await Widgets.UpgradeAsync(Widget.Name);
            _plan = null;
            await OnSaved.InvokeAsync(done.Saved);
        }
        catch (ApiException error)
        {
            _upgradeError = error;
        }
    }

    private async Task DeleteAsync()
    {
        if (!await Dialogs.AskYesNoAsync($"Delete {Widget.Name} from the library?", string.Empty, "Delete", danger: true))
        {
            return;
        }
        try
        {
            await Widgets.DeleteAsync(Widget.Name);
            await OnDeleted.InvokeAsync();
        }
        catch (ApiException error)
        {
            _error = error;
        }
    }
}
