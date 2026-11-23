namespace SwissArmyBench.Web.Api.Extensions;

/// <summary>A code to copy and a page to open (https only), then its action posted.</summary>
public sealed record PanelCode(
    string Label,
    string Text,
    string Link,
    string LinkLabel,
    string Then,
    bool Waiting = false);
