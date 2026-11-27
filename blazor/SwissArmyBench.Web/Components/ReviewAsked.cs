namespace SwissArmyBench.Web.Components;

/// <summary>The comment box asked for in an editor (codeEditor.js reviewAsk): a new comment's range, or the comment
/// being changed (its id and words), and where on the window the box opens.</summary>
public sealed record ReviewAsked(
    int? Id,
    int Line,
    int Column,
    int End,
    int EndColumn,
    double X,
    double Y,
    string Text);
