using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api;
using SwissArmyBench.Web.Api.Workbench;
using SwissArmyBench.Web.State;

namespace SwissArmyBench.Web.Components;

public partial class ReviewPanel
{
    private bool _open = true;
    private bool _sending;
    private string? _error;

    [Inject]
    private AgentInboxClient Inbox { get; set; } = default!;

    [Inject]
    private Notes Notes { get; set; } = default!;

    [Inject]
    private Dialogs Dialogs { get; set; } = default!;

    [Parameter, EditorRequired]
    public ReviewComments Review { get; set; } = default!;

    /// <summary>The document as the agent is told of it: its path, else its tab's title.</summary>
    [Parameter, EditorRequired]
    public string Path { get; set; } = string.Empty;

    /// <summary>The document's editors from the top (a notebook's cells: "cell 3"), so the comments list in its order.</summary>
    [Parameter]
    public Func<IReadOnlyList<string>>? Parts { get; set; }

    /// <summary>The comments changed (the tab's count follows).</summary>
    [Parameter]
    public EventCallback OnChanged { get; set; }

    // A document keeps the one ReviewComments for as long as its tab is open.
    protected override void OnInitialized() => Review.Changed += OnReviewChanged;

    private void OnReviewChanged() => _ = InvokeAsync(async () =>
    {
        StateHasChanged();
        await OnChanged.InvokeAsync();
    });

    /// <summary>Every comment sent as one message; once it went they are all cleared. A send that fails keeps
    /// them and says why.</summary>
    public async Task SendAsync()
    {
        if (_sending || Review.Count == 0)
        {
            return;
        }
        _sending = true;
        _error = null;
        try
        {
            await Review.RefreshAsync();
            var items = Review.Ordered(Parts?.Invoke())
                .Select(c => new ReviewItem(c.Line, Math.Max(c.End, c.Line), c.Code, c.Text, c.Part, c.ByAgent ? "agent" : "user"))
                .ToList();
            var sent = await Inbox.ReviewAsync(Path, items);
            await Review.ClearAsync();
            var masked = sent.Masked > 0 ? $" ({sent.Masked} secret value{(sent.Masked == 1 ? string.Empty : "s")} masked)" : string.Empty;
            await Notes.SayAsync($"Sent {sent.Comments} annotation{(sent.Comments == 1 ? string.Empty : "s")} to the agent{masked}. The file is unchanged.");
        }
        catch (ApiException error)
        {
            _error = error.Refusal.Error;
        }
        catch (HttpRequestException)
        {
            _error = "The app's server did not answer.";
        }
        finally
        {
            _sending = false;
        }
    }

    /// <summary>Every comment thrown away, asked first.</summary>
    public async Task ClearAsync()
    {
        if (Review.Count > 0 && await Dialogs.AskYesNoAsync("Annotations", $"Throw away {Review.CountWords} on {Path}? They were not sent.", "Clear", danger: true))
        {
            await Review.ClearAsync();
        }
    }

    public void Dispose()
    {
        Review.Changed -= OnReviewChanged;
        GC.SuppressFinalize(this);
    }
}
