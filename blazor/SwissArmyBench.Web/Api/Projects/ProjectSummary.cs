using SwissArmyBench.Web.Api.SessionLog;
using SwissArmyBench.Web.Api.Workbench;

namespace SwissArmyBench.Web.Api.Projects;

/// <summary>GET /project/summary: Home's summary of the open project (services/project_summary.py), or a null
/// <see cref="Project"/> with none open.</summary>
public sealed record ProjectSummary(SummaryProject? Project)
{
    public ProjectPythonState? Python { get; init; }

    public IReadOnlyList<SummaryTable> Tables { get; init; } = [];

    public IReadOnlyList<SummaryDocument> Documents { get; init; } = [];

    public IReadOnlyList<SummaryConnection> Connections { get; init; } = [];

    public IReadOnlyList<SessionEntry> Recent { get; init; } = [];

    public SummaryDeliverable? Deliverable { get; init; }

    public SummaryCounts Counts { get; init; } = new();
}
