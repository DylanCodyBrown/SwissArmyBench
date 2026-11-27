using Microsoft.AspNetCore.Components;
using Microsoft.JSInterop;

namespace SwissArmyBench.Web.Components;

// Review comments on this editor's code (the owner, 2026-11-27): select, right-click, Comment… (Ctrl+Alt+M). The
// document's comments (ReviewComments, handed down by the page that holds the document) are drawn here as Monaco
// decorations, never as text; the small box to type one opens at the selection (ReviewCommentBox).
public partial class CodeEditor : IReviewSurface
{
    private ReviewAsked? _asked;
    private ReviewComments? _attachedTo;

    /// <summary>The open document's review comments; null: an editor with no document to comment on.</summary>
    [CascadingParameter]
    public ReviewComments? Review { get; set; }

    /// <summary>Which of the document's editors this is: a notebook's "cell 3"; empty for a file of one editor.</summary>
    [Parameter]
    public string ReviewPart { get; set; } = string.Empty;

    private object ReviewNotes() => (Review?.Of(ReviewPart) ?? []).Select(Drawn).ToList();

    private static object Drawn(ReviewComment c) => new { id = c.Id, line = c.Line, column = c.Column, end = c.End, endColumn = c.EndColumn, text = c.Text, agent = c.ByAgent };

    private void AttachReview()
    {
        _attachedTo = Review;
        Review?.Attach(ReviewPart, this);
    }

    private void DetachReview() => _attachedTo?.Detach(ReviewPart, this);

    [JSInvokable]
    public Task CommentAsk(ReviewAsked asked) => InvokeAsync(() =>
    {
        _asked = asked;
        StateHasChanged();
    });

    [JSInvokable]
    public void CommentsMoved(List<ReviewPlace> places) => Review?.Moved(places);

    private async Task CommentSavedAsync(string text)
    {
        if (_asked is not { } asked || Review is null)
        {
            return;
        }
        _asked = null;
        if (asked.Id is { } id)
        {
            await Review.RewordAsync(id, text);
        }
        else
        {
            var made = await Review.AddAsync(ReviewPart, new ReviewPlace(0, asked.Line, asked.Column, asked.End, asked.EndColumn, string.Empty), text);
            Review.Moved(await PlacesAsync()); // its code, read where it was drawn
            await ShowAsync(made.Id);
        }
    }

    private async Task CommentDeletedAsync()
    {
        if (_asked?.Id is { } id && Review is not null)
        {
            await Review.RemoveAsync(id);
        }
        await CommentClosedAsync();
    }

    private async Task CommentClosedAsync()
    {
        _asked = null;
        await FocusAsync();
    }

    public async Task DrawAsync(ReviewComment comment)
    {
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("addComment", Drawn(comment));
        }
    }

    public async Task RewordAsync(ReviewComment comment)
    {
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("updateComment", comment.Id, comment.Text);
        }
    }

    public async Task EraseAsync(int id)
    {
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("removeComment", id);
        }
    }

    public async Task EraseAllAsync()
    {
        _asked = null;
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("clearComments");
        }
        StateHasChanged();
    }

    public async Task<IReadOnlyList<ReviewPlace>> PlacesAsync() => _editor is null ? [] : await _editor.InvokeAsync<List<ReviewPlace>>("commentPlaces");

    public async Task ShowAsync(int id)
    {
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("revealComment", id);
        }
    }

    public async Task AskAsync(int? id)
    {
        if (_editor is not null)
        {
            await _editor.InvokeVoidAsync("askComment", id);
        }
    }

    public async Task<ReviewPlace?> LinesAsync(int line, int end)
    {
        if (_editor is null)
        {
            return null;
        }
        await _editor.InvokeVoidAsync("selectLines", line, end);
        var text = await _editor.InvokeAsync<string>("selection");
        var lines = text.Split('\n');
        return new ReviewPlace(0, line, 1, line + lines.Length - 1, lines[^1].Length + 1, text);
    }
}
