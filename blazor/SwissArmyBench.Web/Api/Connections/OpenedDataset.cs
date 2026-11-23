using System.Text.Json;

namespace SwissArmyBench.Web.Api.Connections;

/// <summary>POST /connections/{name}/open-dataset: the tables opened and the ones that could not be.</summary>
public sealed record OpenedDataset(IReadOnlyList<JsonElement> Opened, IReadOnlyList<FailedTable> Failed);
