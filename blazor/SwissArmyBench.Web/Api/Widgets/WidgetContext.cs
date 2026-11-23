namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>What the pickers offer (GET /streamlit/widgets/context): the tables and their columns, by group; the variables; every API's actions.</summary>
public sealed record WidgetContext
{
    public IReadOnlyDictionary<string, IReadOnlyList<string>?> Tables { get; init; } = new Dictionary<string, IReadOnlyList<string>?>();

    public IReadOnlyList<string> OpenTables { get; init; } = [];

    public IReadOnlyList<string> DataTables { get; init; } = [];

    public IReadOnlyDictionary<string, IReadOnlyList<string>?> ConnectionTables { get; init; } = new Dictionary<string, IReadOnlyList<string>?>();

    public IReadOnlyList<string> Variables { get; init; } = [];

    public IReadOnlyList<string> Endpoints { get; init; } = [];

    public IReadOnlyDictionary<string, IReadOnlyList<string>> EndpointFields { get; init; } = new Dictionary<string, IReadOnlyList<string>>();
}
