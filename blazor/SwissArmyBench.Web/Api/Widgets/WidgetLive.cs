namespace SwissArmyBench.Web.Api.Widgets;

/// <summary>The properties and contract read from the code as it is typed (POST /streamlit/widgets/properties).</summary>
public sealed record WidgetLive
{
    public IReadOnlyList<WidgetProp> Properties { get; init; } = [];

    public WidgetContract? Contract { get; init; }

    public WidgetProblem? Problem { get; init; }
}
