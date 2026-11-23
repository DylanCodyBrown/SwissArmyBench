namespace SwissArmyBench.Web.Api.Workbench;

/// <summary>POST /projects/dictionary: one of data.ipynb's tables in the data dictionary: its rows, source, steps,
/// description and columns.</summary>
public sealed record DictionaryTable(
    string Table,
    long Rows,
    string Source,
    int Steps,
    string Description,
    IReadOnlyList<DictionaryColumn> Columns);
