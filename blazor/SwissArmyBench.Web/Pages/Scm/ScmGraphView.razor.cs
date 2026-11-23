using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;

using SwissArmyBench.Web.Api.Git;

namespace SwissArmyBench.Web.Pages.Scm;

public partial class ScmGraphView
{
    // The hover card opens beside the row's right edge.
    private const double HoverGap = 6;

    [Parameter]
    public ScmRepository? Repo { get; set; }

    [Parameter]
    public bool SignedIn { get; set; }

    [Parameter]
    public ScmHistory? History { get; set; }

    [Parameter, EditorRequired]
    public Dictionary<string, IReadOnlyList<ScmResource>> Opened { get; set; } = [];

    [Parameter]
    public ShownDiff? Shown { get; set; }

    [Parameter, EditorRequired]
    public ScmPage Host { get; set; } = default!;

    /// <summary>The rows' view models: the history's commits with their refs, and Incoming Changes when GitHub's head
    /// is ahead of the last commit synced here (VS Code's dashed node).</summary>
    private IReadOnlyList<GraphRow> Rows
    {
        get
        {
            var history = History!;
            var local = history.Refs.FirstOrDefault(r => r.Kind == "local");
            var remote = history.Refs.FirstOrDefault(r => r.Kind == "remote");
            var items = history.Rows
                .Select(row => new GraphItem(row.Id, row.Parents, row.Subject, row.Author, row.Date, row.Message,
                    history.Refs.Where(r => r.Commit == row.Id).Select(r => new GraphRef(r.Id, r.Name, r.Kind)).ToList()))
                .ToList();
            if (local is not null && remote is not null && local.Commit != remote.Commit && items.FindIndex(i => i.Id == local.Commit) is > 0 and var at)
            {
                items.Insert(at, new GraphItem(ScmGraph.IncomingId, [local.Commit], "Incoming Changes", string.Empty, string.Empty, string.Empty, []));
            }
            var colors = new[] { (local, ScmGraph.RefColor), (remote, ScmGraph.RemoteRefColor) }
                .Where(p => p.Item1 is not null)
                .ToDictionary(p => p.Item1!.Id, p => (string?)p.Item2);
            return ScmGraph.ViewModels(items, colors, local?.Commit);
        }
    }

    private static string LabelStyle(GraphRef label) =>
        $"color: var(--vscode-scmGraph-historyItemHoverLabelForeground); background-color: {(label.Color is { } c ? $"var(--vscode-{c})" : "var(--vscode-scmGraph-historyItemHoverDefaultLabelBackground)")}";

    private void Hover(MouseEventArgs e, GraphItem item, bool incoming)
    {
        if (!incoming)
        {
            // The row's right edge: the pointer's place less how far in it is, plus the row's width is not known
            // here, so the card opens a little right of the pointer.
            Host.ShowHover(new HoverCard(item, e.ClientX + HoverGap, e.ClientY - e.OffsetY));
        }
    }

    private void Menu(MouseEventArgs e, ScmRepository repo, GraphItem item, bool incoming)
    {
        if (!incoming)
        {
            Host.Menu(e.ClientX, e.ClientY, item.Subject, Host.CommitRowItems(repo, item));
        }
    }
}
