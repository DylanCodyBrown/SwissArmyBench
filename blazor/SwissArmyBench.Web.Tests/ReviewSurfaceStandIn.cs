using SwissArmyBench.Web.Components;

namespace SwissArmyBench.Web.Tests;

/// <summary>An editor stood in for (IReviewSurface): what was drawn on it, and what it was asked to show.</summary>
public sealed class ReviewSurfaceStandIn : IReviewSurface
{
    private readonly string[] _lines;

    public ReviewSurfaceStandIn(string text)
    {
        _lines = text.Split('\n');
    }

    public Dictionary<int, ReviewComment> Drawn { get; } = [];

    public List<int> Shown { get; } = [];

    public List<int?> Asked { get; } = [];

    /// <summary>Lines added above every comment since they were drawn (an edit the editor follows).</summary>
    public int Shift { get; set; }

    public Task DrawAsync(ReviewComment comment)
    {
        Drawn[comment.Id] = comment;
        return Task.CompletedTask;
    }

    public Task RewordAsync(ReviewComment comment) => DrawAsync(comment);

    public Task EraseAsync(int id)
    {
        Drawn.Remove(id);
        return Task.CompletedTask;
    }

    public Task EraseAllAsync()
    {
        Drawn.Clear();
        return Task.CompletedTask;
    }

    public Task<IReadOnlyList<ReviewPlace>> PlacesAsync() => Task.FromResult<IReadOnlyList<ReviewPlace>>(
        Drawn.Values.Select(c => new ReviewPlace(c.Id, c.Line + Shift, c.Column, c.End + Shift, c.EndColumn, c.Code)).ToList());

    public Task ShowAsync(int id)
    {
        Shown.Add(id);
        return Task.CompletedTask;
    }

    public Task AskAsync(int? id)
    {
        Asked.Add(id);
        return Task.CompletedTask;
    }

    public Task<ReviewPlace?> LinesAsync(int line, int end) => Task.FromResult<ReviewPlace?>(
        line > _lines.Length ? null : new ReviewPlace(0, line, 1, end, _lines[end - 1].Length + 1, string.Join('\n', _lines[(line - 1)..end])));
}
