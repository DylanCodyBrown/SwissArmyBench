namespace SwissArmyBench.Web.Api.App;

/// <summary>One page, table or document in a window of its own (GET /pop-outs, the pop_outs notice): its key
/// (page:connections, table:&lt;grid&gt;, doc:&lt;path&gt;), its name, where it is now, whether its window is there.</summary>
public sealed record PopOutEntry(
    string Key,
    string Kind,
    string Name,
    string Address,
    bool Connected,
    string Placeholder,
    bool Existing = false);
