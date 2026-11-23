using SwissArmyBench.Web.Api.Relationships;

namespace SwissArmyBench.Web.Pages.Grids.Compare;

/// <summary>The relationship model's joins between two tables (the classic relationships.ts knownPairs): each as
/// [left column, right column] pairs, the active one first; the same table on both sides lines up on its primary
/// key.</summary>
public static class KnownJoins
{
    public static IReadOnlyList<IReadOnlyList<(string Left, string Right)>> Between(Model model, string left, string right) =>
        model.Relationships
            .Select(r => r.From == left && r.To == right
                ? (r.Active, Pairs: r.FromColumns.Zip(r.ToColumns).ToList())
                : r.From == right && r.To == left
                    ? (r.Active, Pairs: r.ToColumns.Zip(r.FromColumns).ToList())
                    : (r.Active, Pairs: []))
            .Where(j => j.Pairs.Count > 0)
            .OrderByDescending(j => j.Active)
            .Select(j => (IReadOnlyList<(string, string)>)j.Pairs)
            .ToList();

    /// <summary>The known join (the active one), or the primary key when one table is compared with itself.</summary>
    public static IReadOnlyList<(string Left, string Right)> Pairs(Model model, string left, string right)
    {
        var joins = Between(model, left, right);
        if (joins.Count > 0)
        {
            return joins[0];
        }
        if (left == right && model.Tables?.GetValueOrDefault(left)?.PrimaryKey is { } key)
        {
            return key.Select(c => (c, c)).ToList();
        }
        return [];
    }

    /// <summary>Whether two columns are a known join between the tables (any of their joins).</summary>
    public static bool IsKnown(Model model, string left, string right, string leftColumn, string rightColumn)
    {
        var joins = Between(model, left, right);
        var all = joins.Count > 0 ? joins : [Pairs(model, left, right)];
        return all.Any(pairs => pairs.Any(p => p.Left == leftColumn && p.Right == rightColumn));
    }
}
