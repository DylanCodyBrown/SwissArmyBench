namespace SwissArmyBench.Web.Api.Analyze;

/// <summary>POST /analyze/check: Check this table (the data shape check): the table, its notes, every analysis
/// ranked (fits now, after its fixes, or not, with why) and the ones that suit it best.</summary>
public sealed record CheckAnswer(
    string Grid,
    string Dataset,
    string TableLabel,
    long Rows,
    IReadOnlyList<CheckNote> Notes,
    IReadOnlyList<RankedAnalysis> Ranked,
    IReadOnlyList<RankedAnalysis> Top);
