using Microsoft.AspNetCore.Components;

using SwissArmyBench.Web.Api.Grids;

namespace SwissArmyBench.Web.Pages.Grids;

public partial class Ribbon
{
    // The caption names the first two columns, then how many more.
    private const int NamedInCaption = 2;

    [Parameter, EditorRequired]
    public GridInfo Info { get; set; } = default!;

    [Parameter, EditorRequired]
    public GridSelection Selection { get; set; } = GridSelection.None;

    /// <summary>"Connection: Finance", or "Connection…" while it is read.</summary>
    [Parameter]
    public string ConnectionLabel { get; set; } = "Connection…";

    /// <summary>The steps strip, drawn as the Transformations row.</summary>
    [Parameter]
    public RenderFragment? Steps { get; set; }

    /// <summary>The Compare row, drawn only while two grids are side by side.</summary>
    [Parameter]
    public RenderFragment? Compare { get; set; }

    /// <summary>A tool was pressed: its id (the page runs it on the selected columns).</summary>
    [Parameter]
    public EventCallback<string> OnTool { get; set; }

    private IReadOnlyList<string> Target => Selection.Target;

    private string ColumnCaption => Target.Count switch
    {
        0 => string.Empty,
        <= NamedInCaption => string.Join(", ", Target),
        _ => $"{string.Join(", ", Target.Take(NamedInCaption))} +{Target.Count - NamedInCaption}",
    };

    private IEnumerable<RibbonTool> TableTools => RibbonTools.Table(Info, ConnectionLabel);

    private IEnumerable<RibbonTool> ColumnTools => RibbonTools.Column(Info, Target);
}
