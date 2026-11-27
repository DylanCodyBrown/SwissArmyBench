namespace SwissArmyBench.Web.Components;

/// <summary>One review comment on an open document (the owner, 2026-11-27): the lines it covers as the edits have
/// left them, the code there, and what was said. It lives in the page's memory only, never in the file.</summary>
public sealed class ReviewComment
{
    public ReviewComment(int id, string part, string text, bool byAgent)
    {
        Id = id;
        Part = part;
        Text = text;
        ByAgent = byAgent;
    }

    public int Id { get; }

    /// <summary>Which editor of the document it is on: a notebook's "cell 3"; empty for a file of one editor.</summary>
    public string Part { get; }

    public string Text { get; set; }

    /// <summary>A note the agent left to point the user at lines, marked as the agent's.</summary>
    public bool ByAgent { get; }

    public int Line { get; set; }

    public int Column { get; set; }

    public int End { get; set; }

    public int EndColumn { get; set; }

    /// <summary>The code it covers, as last read from the editor.</summary>
    public string Code { get; set; } = string.Empty;

    /// <summary>"line 12", "lines 12-15", "cell 3, line 2".</summary>
    public string Where
    {
        get
        {
            var lines = End > Line ? $"lines {Line}-{End}" : $"line {Line}";
            return Part.Length > 0 ? $"{Part}, {lines}" : lines;
        }
    }

    public void Place(ReviewPlace place)
    {
        Line = place.Line;
        Column = place.Column;
        End = place.End;
        EndColumn = place.EndColumn;
        Code = place.Code;
    }
}
