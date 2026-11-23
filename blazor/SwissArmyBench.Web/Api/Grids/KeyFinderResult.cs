namespace SwissArmyBench.Web.Api.Grids;

/// <summary>POST /grids/{id}/key-finder: the likely join keys with another grid, best first.</summary>
public sealed record KeyFinderResult(string Source, IReadOnlyList<KeyPair> Pairs, int PairCount);
