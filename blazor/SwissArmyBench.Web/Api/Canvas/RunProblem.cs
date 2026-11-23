namespace SwissArmyBench.Web.Api.Canvas;

/// <summary>Why a run did not start (Streamlit missing in this Python: the command that installs it).</summary>
public sealed record RunProblem
{
    public string? Message { get; init; }

    public string? Command { get; init; }
}
