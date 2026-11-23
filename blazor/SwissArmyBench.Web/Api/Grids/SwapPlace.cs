namespace SwissArmyBench.Web.Api.Grids;

/// <summary>A table's place in a connection: database, schema, table (empty parts left out of its words).</summary>
public sealed record SwapPlace(string Database, string Schema, string Table)
{
    public string Words => string.Join(".", new[] { Database, Schema, Table }.Where(p => !string.IsNullOrEmpty(p)));
}
