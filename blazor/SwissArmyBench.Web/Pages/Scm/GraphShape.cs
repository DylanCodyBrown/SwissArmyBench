namespace SwissArmyBench.Web.Pages.Scm;

/// <summary>One shape of a row's graph: a path (its d), or a circle (its centre, radius, stroke width, fill, and a
/// dashed stroke), each in a lane colour.</summary>
public sealed record GraphShape(
    string? Path,
    double Cx,
    double Cy,
    double R,
    double Width,
    string? Stroke,
    string? Fill,
    bool Dashed = false);
