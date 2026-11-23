using System.Text.RegularExpressions;

namespace SwissArmyBench.Web.Pages.Grids;

/// <summary>A DuckDB type's family, as the classic dom.ts tells them apart (which tools and conditions a column
/// takes).</summary>
public static partial class ColumnTypes
{
    public static bool IsNumber(string type) => NumberType().IsMatch(type.ToUpperInvariant());

    public static bool IsText(string type) => type.Equals("VARCHAR", StringComparison.OrdinalIgnoreCase);

    public static bool IsDate(string type) => type.StartsWith("DATE", StringComparison.OrdinalIgnoreCase) || type.StartsWith("TIMESTAMP", StringComparison.OrdinalIgnoreCase);

    public static bool IsBoolean(string type) => type.Equals("BOOLEAN", StringComparison.OrdinalIgnoreCase);

    /// <summary>number, date, boolean or text: the filter's conditions are the family's.</summary>
    public static string Family(string type) => IsNumber(type) ? "number" : IsDate(type) ? "date" : IsBoolean(type) ? "boolean" : "text";

    [GeneratedRegex("^(U?TINYINT|U?SMALLINT|U?INTEGER|U?BIGINT|U?HUGEINT|FLOAT|DOUBLE|REAL|DECIMAL)")]
    private static partial Regex NumberType();
}
