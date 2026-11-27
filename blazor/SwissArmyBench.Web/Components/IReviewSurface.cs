namespace SwissArmyBench.Web.Components;

/// <summary>An editor as the review comments see it (CodeEditor; a stand-in in the tests): the comments drawn on its
/// code, read back where the edits left them, shown, and its comment box opened.</summary>
public interface IReviewSurface
{
    Task DrawAsync(ReviewComment comment);

    Task RewordAsync(ReviewComment comment);

    Task EraseAsync(int id);

    Task EraseAllAsync();

    Task<IReadOnlyList<ReviewPlace>> PlacesAsync();

    Task ShowAsync(int id);

    /// <summary>The comment box opened at a comment (its id), or for the selection (null).</summary>
    Task AskAsync(int? id);

    /// <summary>The whole lines selected (the agent's note names lines).</summary>
    Task<ReviewPlace?> LinesAsync(int line, int end);
}
